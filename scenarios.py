import atomica as at
import utils as ut
import os
import tqdm
from collections import defaultdict
import sciris as sc
import pandas as pd
import matplotlib.pyplot as plt
from utils import plot_emissions, plot_allocation

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

def run_all(P, cobenefits:pd.DataFrame, forbidden_combos:list=None, save:bool=True) -> pd.DataFrame:

    """
    Run all allowed combinations of interventions

    This function produces a dataframe with rows for every allowed combination of interventions,
    with columns for
        - Annual spending by intervention
        - Annual emissions by source
        - Outcomes for annual emissions, annual cost, total cost, and co-benefits

    By default, saves outputs into the `results` folder, although this can be optionally skipped.

    :param P: Atomica project. The first program set (`P.progsets[0]`) will be used automatically. The start year
              is drawn from the project settings. The facility code is drawn from the population name in the project data

    :param progset: Atomica program set.
    :param start_year: Start year of simulations.
    :param forbidden_combos: Optionally specify list of sets of interventions that are mutually exclusive. Only one item from each set may be present in the scenario
    :param save: Optionally save result to `results/all_scenarios_{facility_code}.xlsx` (default: True)
    :return: A dataframe with the simulation outputs
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
    facility_code = results[0].pop_names[0]
    parameters = [par for par in P.framework.pars.index if '_mult' not in par and '_emissions' not in par and '_baseline' not in par]
    par_labels = [par.replace('_', ' ').title() for par in parameters]

    # Populate emissions dataframe
    rows = [res.name for res in results.values()]
    df_emissions = pd.DataFrame(index=rows) #, columns=par_labels)
    for par, par_label in zip(parameters, par_labels):
        for res in results.values():
            df_emissions.loc[res.name, par_label] = res.get_variable(par, facility_code)[0].vals[0]
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
    df['Facility'] = facility_code
    df = df.set_index('Facility', append=True)

    if save:
        with pd.ExcelWriter(f'results/all_scenarios_{facility_code}.xlsx', engine='xlsxwriter') as writer:
            # Apply header colors
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

            # Write the styled dataframe
            x = df.style.apply_index(format, axis="columns")
            x.to_excel(writer, sheet_name=facility_code)

            # Get the xlsxwriter workbook and worksheet objects
            workbook = writer.book
            worksheet = writer.sheets[facility_code]

            # Determine currency formats
            formats = {}
            currency_format = workbook.add_format({'num_format': '$#,##0.00'})

            for program in programs:
                formats[df.columns.get_loc(('Interventions',program.label))+df.index.nlevels] = currency_format
            for cost_col in [('Outcomes','Annual cost'),('Outcomes','Total cost'),('Outcomes','Cost co-benefits')]:
                formats[df.columns.get_loc(cost_col)+df.index.nlevels] = currency_format

            # Determine required column widths
            widths = defaultdict(int)
            for i, (a,b) in enumerate(df.columns):
                widths[i+df.index.nlevels] = max(widths[i+df.index.nlevels], len(a), len(b), df[(a,b)].astype(str).str.len().max())
            for i in range(df.index.nlevels):
                widths[i] = df.index.get_level_values(i).astype(str).str.len().max()

            # Set column formats (both width and cell format)
            for i, width in widths.items():
                worksheet.set_column(i, i, width+3, formats.get(i))

            # Freeze pane - nb. this assumes 2 row index columns, update this cell if the number of index levels changes
            worksheet.freeze_panes('C3')

            # NB. The dataframe can be recreated if needed from the saved file using
            # `df = pd.read_excel(f'results/all_scenarios_{pop}.xlsx', index_col=[0,1], header=[0,1])`

    return df


def save_scenario_outputs(df, facility_code: str, prefix: str):
    """
    Save figures and Excel outputs

    :param df: A subset of the rows from `run_all()` with a single index level containing scenario names
    :param facility_code: The facility code to use
    :param prefix: Prefix to use for the file (e.g., 'optimization' or 'coverage')
    :return:
    """
    # Allocation outputs
    alloc = df['Interventions']
    alloc = alloc.drop('Status-quo')

    # Allocation plot
    fig = plot_allocation(alloc)
    file_name = f'figs/{prefix}_Budget_Allocation_{facility_code}.png'
    fig.savefig(file_name, dpi=300)
    plt.close(fig)
    print(f'Allocation bar plots saved: {file_name}')

    # Budget spreadsheet
    file_name = f'results/{prefix}_Budget_Allocation_{facility_code}.xlsx'
    alloc.T.to_excel(file_name, sheet_name='Budgets')
    print(f'Allocation spreadsheet saved: {file_name}')

    # Emissions outputs
    emissions = df['Emissions']
    emissions.index = [f"${x:,.0f}" if sc.isnumber(x) else x for x in emissions.index]

    # Emissions plot
    fig = plot_emissions(emissions)
    file_name = f'figs/{prefix}_Emissions_{facility_code}.png'
    fig.savefig(file_name, dpi=300)
    plt.close(fig)
    print(f'Emissions bar plots saved: {file_name}')

    # Emissions spreadsheet
    file_name = f'results/{prefix}_Emissions_{facility_code}.xlsx'
    emissions.to_excel(file_name, sheet_name=facility_code)
    print(f'Emissions spreadsheet saved: {file_name}')

    df.index.name='Scenario'
    df['Facility'] = facility_code
    df = df.set_index('Facility',append=True)
    return df




def optimize(df: pd.DataFrame, budgets: list) -> pd.DataFrame:
    """
    Find optimal scenarios for each budget level

    Pass in a dataframe of scenario outputs with the same format as that returned by `run_all()`
    (it would generally just be the same dataframe produced by this function). Pass in a list
    of budgets with maximum spending amounts. Optimal scenarios for each budget level will be
    identified. Plots and spreadsheets of budgets and emissions will be saved to the `figs` and
    `results` directories, respectively. A dataframe containing the optimal scenarios associated
    with each budget level will be returned (the index will be the budget levels, and a 'Status-quo'
    entry, rather than the original scenario name).

    For each budget level, the scenario with the least Annual CO2 emissions and spending less than
    the budget will be identified. If multiple scenarios have the same CO2, the ones with the smallest
    budget will be selected. If multiple scenarios have the same CO2 and cost, pick the one with the
    largest cost co-benefit. In the event that multiple scenarios have the same optimal CO2 level, cost,
    and cost co-benefit, there are intended to be multiple bars for that scenario (i.e., duplicate index
    entries and axis labels). However, this functionality has not been tested as such as scenario has not
    yet been observed.

    :param df: A dataframe with scenario outcomes (generally from `run_all()`)
    :param budgets: Maximum spending amounts
    :return: A dataframe with the same structure as the input, but with scenarios selected and labelled
             according to the requested budget levels
    """

    facility_code = df.index.get_level_values('Facility')[0]
    dfs = []

    df2 = df.loc[df[('Outcomes', 'Total cost')] == 0]
    df2['optimal'] = 'Status-quo'
    dfs.append(df2)

    for budget in budgets:
        df2 = df.loc[df[('Outcomes', 'Annual cost')] <= budget]
        df2 = df2.loc[df2[('Outcomes', 'Annual CO2')] == df2[('Outcomes', 'Annual CO2')].min()]
        df2 = df2.loc[df2[('Outcomes', 'Annual cost')] == df2[('Outcomes', 'Annual cost')].min()]
        df2 = df2.loc[df2[('Outcomes', 'Cost co-benefits')] == df2[('Outcomes', 'Cost co-benefits')].max()]
        df2['optimal'] = budget
        dfs.append(df2)


    df = pd.concat(dfs).set_index('optimal', append=True)
    facility = df.index.get_level_values('Facility')[0]
    df.index = df.index.get_level_values('optimal')

    # Allocation outputs
    df.insert(0, ('Interventions','Surplus budget'),df.index.values[1:] - df['Interventions'][1:].sum(axis=1))

    # Save output files
    save_scenario_outputs(df, facility_code, 'optimization')

    # Prepare final dataframe
    df = df.drop(('Interventions', 'Surplus budget'), axis=1)
    df.index.name='Scenario'
    df['Facility'] = facility_code
    df = df.set_index('Facility',append=True)
    return df

def coverage_scenario(df: pd.DataFrame) -> pd.DataFrame:
    """
    Analyse scenarios with each intervention in isolation

    Pass in a dataframe of scenario outputs with the same format as that returned by `run_all()`
    (it would generally just be the same dataframe produced by this function). A dataframe containing
    the scenarios with each individual intervention will be returned. Plots and spreadsheets of
    budget and emissions will also be generated.

    :param df: A dataframe with scenario outcomes (generally from `run_all()`)
    :param budgets: Maximum spending amounts
    :return: A dataframe with the same structure as the input, but with scenarios selected and labelled
             according to the requested budget levels
    """

    # Extract facility code
    facility_code = df.index.get_level_values('Facility')[0]

    # Find only scenarios with at most 1 intervention
    df = df.loc[df.index.get_level_values('Scenario').map(lambda x: sum(y == '1' for y in x))<=1]

    # Get the corresponding intervention and use it to name the scenario
    scen_names = []
    for _, row in df.iterrows():
        match = row['Interventions'].index[row['Interventions']>0]
        if len(match) == 0:
            scen_names.append('Status-quo')
        else:
            scen_names.append(match[0])
    df.index = scen_names

    # Save output files
    save_scenario_outputs(df, facility_code, prefix='coverage_scenario')

    # Prepare final dataframe
    df.index.name='Scenario'
    df['Facility'] = facility_code
    df = df.set_index('Facility',append=True)
    return df