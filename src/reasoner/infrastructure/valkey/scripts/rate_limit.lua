-- Rate Limiter Lua Script (Token Bucket + Sliding Window)
-- KEYS[1] - Token bucket key (e.g., "rate_limit:client_id:tokens")
-- KEYS[2] - Minute window key (e.g., "rate_limit:client_id:minute")
-- KEYS[3] - Hour window key (e.g., "rate_limit:client_id:hour")
-- ARGV[1] - current_time_ms (milliseconds since epoch)
-- ARGV[2] - refill_rate (tokens per millisecond)
-- ARGV[3] - burst_capacity (max tokens)
-- ARGV[4] - requests_per_minute (max requests in 1 minute)
-- ARGV[5] - requests_per_hour (max requests in 1 hour)
-- ARGV[6] - requested_tokens (usually 1)

local current_time_ms = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local burst_capacity = tonumber(ARGV[3])
local requests_per_minute = tonumber(ARGV[4])
local requests_per_hour = tonumber(ARGV[5])
local requested_tokens = tonumber(ARGV[6])

-- === Token Bucket Logic ===
local bucket_info = redis.call('HMGET', KEYS[1], 'tokens', 'last_refill_time_ms')
local tokens = tonumber(bucket_info[1]) or burst_capacity
local last_refill_time_ms = tonumber(bucket_info[2]) or current_time_ms

local elapsed_time_ms = current_time_ms - last_refill_time_ms
local refilled_tokens = math.floor(elapsed_time_ms * refill_rate)

tokens = math.min(burst_capacity, tokens + refilled_tokens)
last_refill_time_ms = current_time_ms

-- === Sliding Window Logic (Minute) ===
local minute_key = KEYS[2]
redis.call('ZREMRANGEBYSCORE', minute_key, 0, current_time_ms - 60000)
redis.call('ZADD', minute_key, current_time_ms, current_time_ms .. ':' .. math.random()) -- Add current request
local count_minute = redis.call('ZCARD', minute_key)

-- === Sliding Window Logic (Hour) ===
local hour_key = KEYS[3]
redis.call('ZREMRANGEBYSCORE', hour_key, 0, current_time_ms - 3600000)
redis.call('ZADD', hour_key, current_time_ms, current_time_ms .. ':' .. math.random()) -- Add current request
local count_hour = redis.call('ZCARD', hour_key)

-- === Decision ===
local allowed = 0
local retry_after_ms = 0
local reason = "unknown"

if count_minute > requests_per_minute then
    reason = "per_minute_limit"
    local oldest_ts = redis.call('ZRANGE', minute_key, 0, 0, 'WITHSCORES')[2]
    retry_after_ms = 60000 - (current_time_ms - tonumber(oldest_ts))
elseif count_hour > requests_per_hour then
    reason = "per_hour_limit"
    local oldest_ts = redis.call('ZRANGE', hour_key, 0, 0, 'WITHSCORES')[2]
    retry_after_ms = 3600000 - (current_time_ms - tonumber(oldest_ts))
elseif tokens >= requested_tokens then
    allowed = 1
    tokens = tokens - requested_tokens
    reason = "allowed"
else
    reason = "burst_limit"
    -- Calculate time until next token (assuming 1 token needed)
    local tokens_needed = requested_tokens - tokens
    retry_after_ms = math.ceil(tokens_needed / refill_rate)
end

-- Save updated token bucket state only if allowed or if tokens were refilled
if allowed == 1 or refilled_tokens > 0 then
    redis.call('HMSET', KEYS[1], 'tokens', tokens, 'last_refill_time_ms', last_refill_time_ms)
end

-- Return results: [allowed, tokens_remaining, retry_after_ms, reason_code]
return {allowed, math.floor(tokens), math.max(0, math.floor(retry_after_ms)), reason}
