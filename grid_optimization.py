"""
Run three main scenarios.
"""
import numpy as np
from project import P, progset, start_year, facility_code
from scenarios import coverage_scenario, budget_scenario, optimization

# Set random seed
np.random.seed(20232212) # MODIFY AS NEEDED

# Run full coverage scenario
coverage_scenario(P, progset, start_year, facility_code)

# Run budget scenario
spending = 1e4 # MODIFY AS NEEDED
budget_scenario(P, progset, start_year, facility_code, spending)

# Run optimization
budgets = [20e3, 50e3, 100e3] # MODIFY AS NEEDED
optimization(P, progset, start_year, facility_code, budgets)

