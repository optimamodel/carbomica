import atomica as at
from project import P, start_year
import os
if not os.path.exists('results'): os.makedirs('results')
if not os.path.exists('figs'): os.makedirs('figs')
'''
Script to check output of programs under certain coverage and budget conditions.
E.g.: It can be useful to set intervention effects to 0 (perfect effect), the same unit_cost for all interventions, and check that spending (0.5 x unit_cost) or (1 x unit_cost) produces the correct outputs (a program effect of 0.5 or 0, respectively).

'''

# Run a budget scenario and verify that outputs make sense
investment = 1e5  # set investment
progset = P.progsets[0]

# Scale up each prog to see impact
for prog in progset.programs.keys():
    instructions_spending = at.ProgramInstructions(start_year=start_year, alloc={prog: investment})
    budget_res = P.run_sim(P.parsets[0],progset=P.progsets[0], progset_instructions=instructions_spending, result_name=prog)
    budget_res.export_raw('results/budget_raw_{}'.format(prog))

# Run a zero- and full-coverage scenario and verify that outputs make sense
# Zero-coverage of programs
no_coverage = {prog: 0 for prog in progset.programs.keys()}
instructions_cov = at.ProgramInstructions(start_year=start_year, coverage=no_coverage)
no_coverage_res = P.run_sim(P.parsets[0], progset=P.progsets[0], progset_instructions=instructions_cov, result_name='no_coverage')
no_coverage_res.export_raw('results/no_coverage_raw')

# Full coverage of all programs
coverage = {prog: 1 for prog in progset.programs.keys()} 
instructions_cov = at.ProgramInstructions(start_year=start_year, coverage=coverage)
coverage_res = P.run_sim(P.parsets[0], progset=P.progsets[0], progset_instructions=instructions_cov, result_name="Full")
coverage_res.export_raw('results/full_coverage_raw')

# Scale up each prog individually to see impact
for prog in progset.programs.keys():
    instructions_cov = at.ProgramInstructions(start_year=start_year, coverage={prog: 1})
    coverage_prog_res = P.run_sim(P.parsets[0], progset=P.progsets[0], progset_instructions=instructions_cov, result_name=prog)
    coverage_prog_res.export_raw('results/full_coverage_raw_{}'.format(prog))
