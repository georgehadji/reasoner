# vulture false positives for scripts/vulture_ratchet.py.
#
# One line per symbol vulture cannot see used (a descriptor, a getattr target, a
# framework hook), each with the reason. `python -m vulture src/ --make-whitelist`
# prints candidate lines in this format. Adding one lowers the count, so lower
# --max in test.yml and ci-local.sh in the same change.
