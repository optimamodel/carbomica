"""
Run three main scenarios.
"""
import numpy as np
from project import P
from scenarios import coverage_scenario, budget_scenario, run_all, optimize

# Set random seed
np.random.seed(20232212) # MODIFY AS NEEDED

# Run optimization via all scenarios
df = run_all(P)

# Return optimal budgets at various levels
budgets = [20e3, 50e3, 100e3, 200e3, 250e3] # MODIFY AS NEEDED
df_optimization = optimize(df, budgets)

# Coverage scenarios (extracted from full run)
df_coverage = coverage_scenario(df)

# Run budget scenarios
spending = 1e4 # MODIFY AS NEEDED
df_budget = budget_scenario(P, spending)