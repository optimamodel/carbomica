"""
Run three main scenarios.
"""
import numpy as np
from project import P, start_year, facility_code, cobenefits, exclusions
from scenarios import coverage_scenario, budget_scenario, run_all, optimize

# Set random seed
np.random.seed(20232212) # MODIFY AS NEEDED

# # Run full coverage scenario
# coverage_scenario(P, start_year, facility_code)
#
# # Run budget scenario
# spending = 1e4 # MODIFY AS NEEDED
# budget_scenario(P, start_year, facility_code, spending)
#
# # Run optimization via all scenarios
df = run_all(P, cobenefits, exclusions)

# Return optimal budgets at various levels
budgets = [20e3, 50e3, 100e3, 200e3] # MODIFY AS NEEDED
optimize(df, budgets)