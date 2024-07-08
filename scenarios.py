import atomica as at
import utils as ut
import os
import tqdm
import sciris as sc
import pandas as pd
import openpyxl
from collections import defaultdict

if not os.path.exists('results'): os.makedirs('results')
if not os.path.exists('figs'): os.makedirs('figs')


def coverage_scenario(P, start_year, facility_code):
    '''
    Run a scenario where interventions are individually fully covered.
    Results on emission reductions are saved in an excel sheet.
    :param P: Atomica project.
    :param start_year: Start year of simulations.
    :param facility_code: Code of the facility.
    :return: 
    '''
    results_scenario = [P.run_sim(parset='default',result_name='Status-quo')] # run status-quo
    progset = P.progsets[0]

    for prog in progset.programs:
        coverage_scenario = {prog_all: 0 for prog_all in progset.programs}
        coverage_scenario[prog] = 1
        instructions = at.ProgramInstructions(start_year=start_year, coverage=coverage_scenario) # define program instructions
        result_coverage = P.run_sim(parset='default',progset=P.progsets[0], progset_instructions=instructions, result_name=progset.programs[prog].label) # run budget scenario
        results_scenario.append(result_coverage)
        
    # Calculate emissions 
    ut.calc_emissions(results_scenario,start_year,facility_code,file_name='coverage_scenario_Emissions_{}'.format(facility_code),title='CO2e emissions - full coverage')

def budget_scenario(P, start_year, facility_code, spending:int):
    '''
    Run a scenario where spending on interventions are individually specified.
    Results on emission reductions are saved in an excel sheet.
    :param P: Atomica project.
    :param start_year: Start year of simulations.
    :param facility_code: Code of the facility.
    :param spending: Spending on individual interventions.
    :return: 
    '''
    results_scenario = [P.run_sim(parset='default',result_name='Status-quo')] # run status-quo
    progset = P.progsets[0]

    for prog in progset.programs:
        budget_scenario = {prog_all: 0 for prog_all in progset.programs}
        budget_scenario[prog] = spending
        instructions = at.ProgramInstructions(start_year=start_year, alloc=budget_scenario) # define program instructions
        result_budget = P.run_sim(parset='default',progset=P.progsets[0], progset_instructions=instructions, result_name=progset.programs[prog].label) # run budget scenario
        results_scenario.append(result_budget)
        
    # Calculate emissions 
    ut.calc_emissions(results_scenario,start_year,facility_code,file_name='budget_scenario_Emissions_{}'.format(facility_code),title='CO2e emissions - fixed budget (${:0,.0f})'.format(spending))

def optimization(P, start_year, facility_code, budgets:list):
    '''
    Optimize spending allocation on interventions by minizing emissions for a set total budget.
    Results on emission reductions and optimized budget allocations are saved in an excel sheet.
    :param P: Atomica project.
    :param start_year: Start year of simulations.
    :param facility_code: Code of the facility.
    :param budgets: List of budgets to optimize.
    :return: 
    '''
    progset = P.progsets[0]
    instructions = at.ProgramInstructions(alloc=P.progsets[0], start_year=start_year) # Baseline spending
    adjustments = [at.SpendingAdjustment(prog, start_year, 'abs', 0.0, 10e6) for prog in progset.programs] # Adjustments (no spending constraint on any intervention)
    measurables = [at.MinimizeMeasurable('co2e_emissions',start_year)] # Measurables (objective function: minimize total emissions)
    
    # Run optimization
    # Initialize with PSO
    result_names = []
    for budget in budgets:
        result_names.append('${:0,.0f}'.format(budget))
        
    results_optimized = []
    for budget, name in zip(budgets, result_names):
        constraints = at.TotalSpendConstraint(total_spend=budget, t=start_year) # constraint on total spending
        # Run optimization
        optimization = at.Optimization(name='default', method='pso', 
                                       adjustments=adjustments, measurables=measurables, constraints=constraints)
        optimized_instructions = at.optimize(P, optimization, P.parsets[0],P.progsets[0], instructions=instructions, optim_args={"maxiter": 10})
        result_optimized = P.run_sim(P.parsets[0],P.progsets[0], progset_instructions=optimized_instructions)
        
        # Compile results
        result_optimized.name = name
        results_optimized.append(result_optimized)
    
    # Extract spending to use as initial conditions in ASD loop
    allocation_initial, _ = ut.write_alloc_excel(progset, results_optimized, start_year, print_results=False)
    
    # Refine optimization with ASD
    results_optimized = [P.run_sim(parset='default',result_name='Status-quo')]
    for budget, name in zip(budgets, result_names):
        constraints = at.TotalSpendConstraint(total_spend=budget, t=start_year) # constraint on total spending
        adjustments = [at.SpendingAdjustment(prog, start_year, initial=allocation_initial[name][progset.programs[prog].label]) for prog in progset.programs.keys()]
        
        # Run optimization
        optimization = at.Optimization(name='default', method='asd', 
                                       adjustments=adjustments, measurables=measurables, constraints=constraints)
        optimized_instructions = at.optimize(P, optimization, P.parsets[0],P.progsets[0], instructions=instructions)
        result_optimized = P.run_sim(P.parsets[0],P.progsets[0], progset_instructions=optimized_instructions)
        
        # Compile results
        result_optimized.name = name
        results_optimized.append(result_optimized)
        
    # Plot and save emissions
    ut.calc_emissions(results_optimized,start_year,facility_code,file_name='optimization_Emissions_{}'.format(facility_code))
    
    # Plot budget allocation (exclude status-quo result)
    ut.plot_allocation(results_optimized[1:],file_name='optimization_Budget_Allocation_{}'.format(facility_code)) # allocation
    
    # Save budget allocation and interventions coverage (exclude status-quo result)
    ut.write_alloc_excel(progset, results_optimized[1:], start_year,file_name='results/optimization_Budget_Allocation_{}'.format(facility_code))

def run_all(P, cobenefits, forbidden_combos):
    """
    Optimize spending allocation on interventions by minimizing emissions for a set total budget.
    Results on emission reductions and optimized budget allocations are saved in an excel sheet.
    :param P: Atomica project.
    :param progset: Atomica program set.
    :param start_year: Start year of simulations.
    :param budgets: List of budgets to optimize.
    :param baseline_spending: Baseline spending amount.
    :param forbidden_combos: Combinations of programs that are mutually exclusive.
    """

    #generate all program combos
    combos = [combo for combo in ut.powerset(P.progsets[0].programs) if not ut.is_forbidden_combination(combo, forbidden_combos)]

    #run sims of all allowed program combinations
    results = sc.odict()
    programs = P.progsets[0].programs.values()
    with at.Quiet():
        for combo in tqdm.tqdm(combos):
            alloc = {p.name: p.unit_cost.assumption if p.name in combo else 0 for p in programs}
            instructions = at.ProgramInstructions(start_year=P.settings.sim_start, alloc=alloc) # define program instructions
            results[combo] = P.run_sim(parset='default', progset=P.progsets[0], progset_instructions=instructions, result_name='S'+''.join(['1' if p.name in combo else '0' for p in programs]))  # run scenario

    # Calculate emissions/costs and output dataframe
    pop = results[0].pop_names[0]
    pars = results[0].par_names(pop)
    parameters = [par for par in pars if '_mult' not in par and '_emissions' not in par and '_baseline' not in par]
    par_labels = [par.replace('_', ' ').title() for par in parameters]

    # Populate emissions dataframe
    rows = [res.name for res in results.values()]
    df_emissions = pd.DataFrame(index=rows) #, columns=par_labels)
    for par, par_label in zip(parameters, par_labels):
        for res in results.values():
            df_emissions.loc[res.name, par_label] = res.get_variable(par, pop)[0].vals[0]
    df_emissions.columns = pd.MultiIndex.from_product([['Emissions']] + [df_emissions.columns.values])

    # Populate the products in use
    df_programs = pd.DataFrame(index=rows, columns=[p.label for p in programs], dtype=float)
    for k, res in results.items():
        for program in programs:
            df_programs.loc[res.name, program.label] = res.model.program_instructions.alloc[program.name].interpolate(P.settings.sim_start)
    df_programs.columns = pd.MultiIndex.from_product([['Interventions']] + [df_programs.columns.values])

    # Populate costs and co-benefits
    df_outcomes = pd.DataFrame(index=rows, columns=['Annual cost','Total cost','Cost co-benefits','Other co-benefits'])
    for k, res in results.items():
        df_outcomes.loc[res.name, 'Annual cost'] = sum(x.interpolate(P.settings.sim_start)[0] for x in res.model.program_instructions.alloc.values())
        df_outcomes.loc[res.name, 'Total cost']  = sum([x.vals[0] for x in at.PlotData.programs(res, t_bins='all').series])
        cost_cobenefit = 0
        other_cobenefits = []
        for program in k:
            cost_cobenefit += cobenefits.at[program, 'Cost co-benefits']
            if not pd.isna(cobenefits.at[program, 'Other co-benefits']):
                other_cobenefits.append(cobenefits.at[program, 'Other co-benefits'])
        df_outcomes.loc[res.name, 'Cost co-benefits'] = cost_cobenefit
        df_outcomes.loc[res.name, 'Other co-benefits'] = ', '.join(other_cobenefits)
    df_outcomes.columns = pd.MultiIndex.from_product([['Outcomes']] + [df_outcomes.columns.values])
    df_outcomes.insert(0, ('Outcomes','Annual CO2'), df_emissions.sum(axis=1))

    # Assemble the final dataframe
    df = pd.concat([df_programs, df_emissions, df_outcomes], axis=1)
    df.index.name = 'Scenario'
    df['Facility'] = pop
    df = df.set_index('Facility', append=True)
    with pd.ExcelWriter(f'results/all_scenarios_{pop}.xlsx', engine='xlsxwriter') as writer:

        def format(_):
            s = df.columns.get_level_values(0)
            out = []
            for val in s:
                if val == 'Interventions':
                    color = "#fbb4ae"
                elif val == "Emissions":
                    color =" #b3cde3"
                elif val == "Outcomes":
                    color = "#ccebc5"
                out.append(f"background-color: {color};border-color: black; border-width: 1px; border-style: solid;text-align:center;font-weight:bold;")
            return out
        x = df.style.apply_index(format, axis="columns")
        x.to_excel(writer, sheet_name=pop)

        # Get the xlsxwriter workbook and worksheet objects
        workbook = writer.book
        worksheet = writer.sheets[pop]

        # Assign currency formats
        formats = {}
        currency_format = workbook.add_format({'num_format': '$#,##0.00'})

        for program in programs:
            formats[df.columns.get_loc(('Interventions',program.label))+df.index.nlevels] = currency_format
        for cost_col in [('Outcomes','Annual cost'),('Outcomes','Total cost'),('Outcomes','Cost co-benefits')]:
            formats[df.columns.get_loc(cost_col)+df.index.nlevels] = currency_format

        # Calculate the required column widths
        widths = defaultdict(int)
        for i, (a,b) in enumerate(df.columns):
            widths[i+df.index.nlevels] = max(widths[i+df.index.nlevels], len(a), len(b), df[(a,b)].astype(str).str.len().max())
        for i in range(df.index.nlevels):
            widths[i] = df.index.get_level_values(i).astype(str).str.len().max()

        # Set column formats
        for i, width in widths.items():
            worksheet.set_column(i, i, width+3, formats.get(i))

        # Freeze pane - nb. this assumes 2 row index columns, update this cell if the number of index levels changes
        worksheet.freeze_panes('C3')

    # NB. This dataframe can be recreated from the saved file using
    # `df = pd.read_excel(f'results/all_scenarios_{pop}.xlsx', index_col=[0,1], header=[0,1])`

    return df





# def optimize(df)