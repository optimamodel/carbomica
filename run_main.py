"""
Run three main scenarios.
"""
import numpy as np
from project import P, start_year, facility_code, cobenefits, exclusions
from scenarios import coverage_scenario, budget_scenario, optimization, run_all

# Set random seed
np.random.seed(20232212) # MODIFY AS NEEDED

# Run full coverage scenario
coverage_scenario(P, start_year, facility_code)

# Run budget scenario
spending = 1e4 # MODIFY AS NEEDED
budget_scenario(P, start_year, facility_code, spending)

df = run_all(P, cobenefits, exclusions)