import atomica as at
import utils as ut
import os
import tqdm
import sciris as sc
import pandas as pd
from utils import save_scenario_outputs
from project import facility_code, exclusions

if not os.path.exists('results'): os.makedirs('results')
if not os.path.exists('figs'): os.makedirs('figs')


def budget_scenario(P: at.Project, spending:int) -> pd.DataFrame:
    '''
    Run a scenario where spending on interventions are individually specified.
    Results on emission reductions are saved in an Excel sheet.

    :param P: Atomica project.
    :param start_year: Start year of simulations.
    :param spending: Annual spending on individual interventions.
    :return: 
    '''
    progset = P.progsets[0]

    budget_scenario = {prog_all: 0 for prog_all in progset.programs}
    results_scenario = [P.run_sim(parset='default', progset=P.progsets[0], progset_instructions=at.ProgramInstructions(start_year=P.settings.sim_start,alloc=budget_scenario) , result_name='Status-quo')]

    for prog in progset.programs:
        budget_scenario = {prog_all: 0 for prog_all in progset.programs}
        budget_scenario[prog] = spending
        instructions = at.ProgramInstructions(start_year=P.settings.sim_start, alloc=budget_scenario) # define program instructions
        result_budget = P.run_sim(parset='default',progset=P.progsets[0], progset_instructions=instructions, result_name=progset.programs[prog].label) # run budget scenario
        results_scenario.append(result_budget)
        
    # Prepare and save outputs
    df = ut.calc_emissions(results_scenario)

    df_plot = df.copy()
    df_plot.index = df_plot.index.droplevel(1)
    df = save_scenario_outputs(df_plot, f'budget_scenario_{int(spending)}',title_suffix=f'fixed budget (${spending:,.0f})')

    return df

def run_all(P: at.Project, save:bool=True) -> pd.DataFrame:

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
    programs = P.progsets[0].programs
    combos = [combo for combo in ut.powerset(programs) if not ut.is_forbidden_combination(combo, exclusions)]

    #run sims of all allowed program combinations
    results = sc.odict()
    with at.Quiet():
        for combo in tqdm.tqdm(combos):
            alloc = {p.name: p.unit_cost.assumption if p.name in combo else 0 for p in programs.values()}
            instructions = at.ProgramInstructions(start_year=P.settings.sim_start, alloc=alloc) # define program instructions
            results[combo] = P.run_sim(parset='default', progset=P.progsets[0], progset_instructions=instructions, result_name='S'+''.join(['1' if p in combo else '0' for p in programs]))  # run scenario

    df = ut.calc_emissions(list(results.values()))

    if save:
        ut.save_formatted_results(df, f'results/all_scenarios_{facility_code}.xlsx')

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
             according to the requested budget levels. An additional intervention will be added called
             'Surplus budget' containing any unspent funds associated with each scenario.
    """

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
    df.index = df.index.get_level_values('optimal')

    # Allocation outputs

    df = df.reset_index()
    df.insert(0, ('Interventions','Surplus budget'),df['optimal'].values[1:] - df['Interventions'][1:].sum(axis=1))
    df = df.set_index('optimal')

    # Rename the scenarios with proper formatting
    df.index = [f"${x:,.0f}" if sc.isnumber(x) else x for x in df.index]

    # Save output files
    df = save_scenario_outputs(df, 'optimization')

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

    # Save outputs
    df = save_scenario_outputs(df, 'coverage_scenario')

    return df