-- Circuit Breaker Lua Script (shared state across workers)
-- KEYS[1] - Circuit breaker key (e.g., "cb:openai/gpt-4o")
-- ARGV[1] - Operation: "can_execute" | "record_success" | "record_failure"
-- ARGV[2] - current_time_ms (wall-clock Unix ms)
--
-- Operation-specific args:
--   can_execute:  ARGV[3]=timeout_ms, ARGV[4]=max_half_open_calls
--   record_success: ARGV[3]=success_threshold
--   record_failure: ARGV[3]=failure_threshold

local op = ARGV[1]
local key = KEYS[1]
local ttl_seconds = 604800  -- 7 days

-- Helper: refresh TTL on every operation
local function refresh_ttl()
    redis.call('EXPIRE', key, ttl_seconds)
end

-- Helper: get current state fields
local function get_state()
    local fields = redis.call('HGETALL', key)
    local state = {}
    for i = 1, #fields, 2 do
        state[fields[i]] = fields[i + 1]
    end
    return state
end

if op == "can_execute" then
    local current_ms = tonumber(ARGV[2])
    local timeout_ms = tonumber(ARGV[3])
    local max_half_open_calls = tonumber(ARGV[4])

    local state = get_state()
    local current_state = state["state"] or "CLOSED"
    local half_open_calls = tonumber(state["half_open_calls"]) or 0

    if current_state == "OPEN" then
        local last_state_change_ms = tonumber(state["last_state_change_ms"]) or 0
        if (current_ms - last_state_change_ms) >= timeout_ms then
            -- transition OPEN → HALF_OPEN, reset counters, allow this call
            redis.call('HSET', key,
                'state', 'HALF_OPEN',
                'consecutive_successes', 0,
                'half_open_calls', 1,
                'last_state_change_ms', current_ms
            )
            refresh_ttl()
            return {1, 'HALF_OPEN'}
        end
        refresh_ttl()
        return {0, 'OPEN'}
    elseif current_state == "HALF_OPEN" then
        if half_open_calls >= max_half_open_calls then
            refresh_ttl()
            return {0, 'HALF_OPEN_FULL'}
        end
        redis.call('HINCRBY', key, 'half_open_calls', 1)
        refresh_ttl()
        return {1, 'HALF_OPEN'}
    else  -- CLOSED
        refresh_ttl()
        return {1, 'CLOSED'}
    end

elseif op == "record_success" then
    local success_threshold = tonumber(ARGV[3])

    local state = get_state()
    local current_state = state["state"] or "CLOSED"

    if current_state == "HALF_OPEN" then
        redis.call('HINCRBY', key, 'consecutive_successes', 1)
        redis.call('HINCRBY', key, 'half_open_calls', -1)
        local consecutive_successes = tonumber(
            redis.call('HGET', key, 'consecutive_successes')
        ) or 0
        if consecutive_successes >= success_threshold then
            redis.call('HSET', key,
                'state', 'CLOSED',
                'consecutive_failures', 0,
                'consecutive_successes', 0,
                'half_open_calls', 0
            )
        end
    elseif current_state == "CLOSED" then
        redis.call('HSET', key, 'consecutive_failures', 0)  -- reset streak on success
    end

    refresh_ttl()
    return {1, current_state}

elseif op == "record_failure" then
    local failure_threshold = tonumber(ARGV[3])
    local current_ms = tonumber(ARGV[2])

    local state = get_state()
    local current_state = state["state"] or "CLOSED"

    if current_state == "HALF_OPEN" then
        -- Any failure in HALF_OPEN immediately reopens
        redis.call('HSET', key,
            'state', 'OPEN',
            'consecutive_failures', 0,
            'consecutive_successes', 0,
            'last_state_change_ms', current_ms
        )
        redis.call('HINCRBY', key, 'half_open_calls', -1)
    elseif current_state == "CLOSED" then
        redis.call('HINCRBY', key, 'consecutive_failures', 1)
        local consecutive_failures = tonumber(
            redis.call('HGET', key, 'consecutive_failures')
        ) or 0
        if consecutive_failures >= failure_threshold then
            redis.call('HSET', key,
                'state', 'OPEN',
                'last_state_change_ms', current_ms
            )
        end
    end

    refresh_ttl()
    return {1, current_state}

else
    return {0, 'UNKNOWN_OPERATION'}
end
