import matplotlib.pyplot as plt
import matplotlib as mpl
import pandas as pd
import atomica as at
import itertools
import sciris as sc
from project import cobenefits, emissions_pars

def calc_emissions(results):
    '''
    Calculate all simulation outputs (emissions and costs)

    :param results: list of Atomica result objects.
    '''

    programs = results[0].model.progset.programs.values()
    facility_code = results[0].pop_names[0]
    start_year = results[0].t[0]

    # Calculate emissions/costs and output dataframe
    par_labels = [par.replace('_', ' ').title() for par in emissions_pars]


    # Populate emissions dataframe
    rows = [res.name for res in results]
    df_emissions = pd.DataFrame(index=rows) #, columns=par_labels)
    for par, par_label in zip(emissions_pars, par_labels):
        for res in results:
            df_emissions.loc[res.name, par_label] = res.get_variable(par, facility_code)[0].vals[0]
    df_emissions.columns = pd.MultiIndex.from_product([['Emissions']] + [df_emissions.columns.values])

    # Populate the products in use
    df_programs = pd.DataFrame(index=rows, columns=[p.label for p in programs], dtype=float)
    for res in results:
        for program in programs:
            df_programs.loc[res.name, program.label] = res.model.program_instructions.alloc[program.name].interpolate(start_year)
    df_programs.columns = pd.MultiIndex.from_product([['Interventions']] + [df_programs.columns.values])

    # Populate costs and co-benefits
    df_outcomes = pd.DataFrame(index=rows, columns=['Annual cost','Total cost','Cost co-benefits','Other co-benefits'])
    for res in results:
        df_outcomes.loc[res.name, 'Annual cost'] = sum(x.interpolate(start_year)[0] for x in res.model.program_instructions.alloc.values())
        df_outcomes.loc[res.name, 'Total cost']  = sum([x.vals[0] for x in at.PlotData.programs(res, t_bins='all').series])
        cost_cobenefit = 0
        other_cobenefits = []
        programs_funded = set()
        for program in programs:
            if res.model.program_instructions.alloc[program.name].interpolate(start_year):
                programs_funded.add(program.name)
        for program in programs_funded:
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

    return df


def plot_allocation(df: pd.DataFrame, title_suffix:str=None) -> plt.Figure:
    '''
    Plot a bar graph of spending by intervention for each scenario

    :param df: A dataframe where the index is the name of the scenario, and the columns are interventions. If a
               column called 'Surplus budget' is provided, it will be plotted with a hatched pattern
    :param title_suffix: Optionally specify a suffix to append to the title
    :return: A matplotlib figure
    '''

    # Select colormap
    # colormap = plt.cm.tab20     # https://matplotlib.org/stable/users/explain/colors/colormaps.html#qualitative
    # colors = [colormap(i) for i in range(len(df.columns))]
    colors = sc.gridcolors(df.shape[1])

    fig, ax = plt.subplots()
    df.iloc[:,::-1].plot.bar(stacked=True, color=colors, ax=ax, fontsize=22)
    fig.set_size_inches(len(df)*2.5+6,10)

    # Apply hatched pattern to "Surplus budget" bars
    for bar, label in zip(ax.patches, df.columns[::-1].repeat(df.shape[0])):
        if label == "Surplus budget":
            bar.set_hatch('//')  # Applying hatched pattern

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc='upper left', bbox_to_anchor=(1.05, 1), title='Interventions', fontsize=20, title_fontsize=22)
    ax.set_xticklabels(df.index, rotation=0 if df.index.str.len().max() < 12 else 90)
    ax.yaxis.set_major_formatter(mpl.ticker.StrMethodFormatter('${x:,.0f}'))
    ax.set_title('Budget allocation' + (f' - {title_suffix}' if title_suffix else ''), fontsize=25)
    ax.set_xlabel(None)
    fig.tight_layout()
    return fig


def plot_emissions(df: pd.DataFrame, title_suffix:str=None) -> plt.Figure:
    """
    Plot a bar graph of emissions by category for each scenario

    :param df: A dataframe where the index has the name of the scenario, and the columns are names of emissions sources
    :param title_suffix: Optionally specify a suffix to append to the title
    :return: A matplotlib Figure
    """

    font_size = 22
    colors = None # sc.gridcolors(df.shape[1]) # Original code had no special colormap

    fig, ax = plt.subplots()
    df.iloc[:, ::-1].plot.bar(stacked=True, color=colors, ax=ax, fontsize=font_size)

    plt.title("Total CO2e Emissions" + (f' - {title_suffix}' if title_suffix else ''), fontsize=font_size + 2)

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], title='Emission Sources', bbox_to_anchor=(1.0, 1.0), loc='upper left', fontsize=font_size - 2, title_fontsize=font_size)

    ax.yaxis.set_major_formatter(mpl.ticker.StrMethodFormatter('{x:,.0f}'))
    ax.set_xticklabels(df.index, ha='center', rotation=90)
    ax.set_xlabel(None)
    ax.set_ylabel('Emissions (CO2e)', fontsize=font_size)

    fig.set_size_inches(max(15, len(df) * 1.5), 10)
    fig.tight_layout()

    return fig


def powerset(set):
    """
    Return all combinations of length 0-n

    For example, given the collection [1,2,3] this function would return
    [],[1],[2],[3],[1,2],[1,3],[2,3],[1,2,3]

    :param set: Iterable of items (set, list)
    :return: Generator of all combinations
    """
    return itertools.chain.from_iterable(itertools.combinations(set, r) for r in range(len(set) + 1))


def is_forbidden_combination(combo, forbidden=None):
    """
    Check if a given set of programs contains a subset of programs that is forbidden
    :param combo: List of programs
    :param forbidden: List of forbidden program combinations
    :return: Boolean, True if program list contains a forbidden combination
    """
    if forbidden is not None:
        for f in forbidden:
            if len(f & set(combo)) > 1:
                return True
    return False
