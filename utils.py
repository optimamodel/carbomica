import matplotlib.pyplot as plt
import matplotlib as mpl
import pandas as pd
import atomica as at
import itertools
import sciris as sc
from project import cobenefits, emissions_pars, facility_code
from collections import defaultdict

def calc_emissions(results: list) -> pd.DataFrame:
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


def save_formatted_results(df, file_name):
    with pd.ExcelWriter(file_name, engine='xlsxwriter') as writer:
        # Apply header colors
        def format(_):
            s = df.columns.get_level_values(0)
            out = []
            for val in s:
                if val == 'Interventions':
                    color = "#fbb4ae"
                elif val == "Emissions":
                    color = " #b3cde3"
                elif val == "Outcomes":
                    color = "#ccebc5"
                out.append(f"background-color: {color};border-color: black; border-width: 1px; border-style: solid;text-align:center;font-weight:bold;")
            return out

        # Write the styled dataframe
        x = df.style.apply_index(format, axis="columns")
        x.to_excel(writer)

        # Get the xlsxwriter workbook and worksheet objects
        workbook = writer.book
        worksheet = workbook.worksheets()[0]

        # Determine currency formats
        formats = {}
        currency_format = workbook.add_format({'num_format': '$#,##0.00'})

        for program in df['Interventions'].columns:
            formats[df.columns.get_loc(('Interventions', program)) + df.index.nlevels] = currency_format
        for cost_col in [('Outcomes', 'Annual cost'), ('Outcomes', 'Total cost'), ('Outcomes', 'Cost co-benefits')]:
            formats[df.columns.get_loc(cost_col) + df.index.nlevels] = currency_format

        # Determine required column widths
        widths = defaultdict(int)
        for i, (a, b) in enumerate(df.columns):
            widths[i + df.index.nlevels] = max(widths[i + df.index.nlevels], len(a), len(b), df[(a, b)].astype(str).str.len().max())
        for i in range(df.index.nlevels):
            widths[i] = df.index.get_level_values(i).astype(str).str.len().max()

        # Set column formats (both width and cell format)
        for i, width in widths.items():
            worksheet.set_column(i, i, width + 3, formats.get(i))

        # Freeze pane - nb. this assumes 2 row index columns, update this cell if the number of index levels changes
        worksheet.freeze_panes('C3')

        # NB. The dataframe can be recreated if needed from the saved file using
        # `df = pd.read_excel(f'results/all_scenarios_{pop}.xlsx', index_col=[0,1], header=[0,1])`


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


def save_scenario_outputs(df, prefix: str, title_suffix: str = None):
    """
    Save all figures and Excel outputs associated with a scenario

    :param df: A subset of the rows from `run_all()` with a single index level containing scenario names
    :param prefix: Prefix to use for the file (e.g., 'optimization' or 'coverage')
    :param title_suffix: Optional string to append to the plot titles
    :return:
    """

    # Allocation outputs
    alloc = df['Interventions']
    alloc = alloc.drop('Status-quo')

    # Allocation plot
    fig = plot_allocation(alloc, title_suffix)
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

    # Emissions plot
    fig = plot_emissions(emissions, title_suffix)
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
    save_formatted_results(df, f'results/{prefix}_{facility_code}.xlsx')
    return df


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
