import matplotlib.pyplot as plt
import matplotlib as mpl
import pandas as pd
import atomica as at
import itertools
import sciris as sc
from project import cobenefits, emissions_pars, facility_code
from collections import defaultdict
import numpy as np

def calc_emissions(results: list) -> pd.DataFrame:
    '''
    Calculate all simulation outputs (emissions and costs)

    :param results: list of Atomica result objects.
    '''

    programs = results[0].model.progset.programs.values()
    facility_code = results[0].pop_names[0]
    start_year = results[0].t[0]

    # Calculate spending on each intervention
    rows = [res.name for res in results]
    df_programs = pd.DataFrame(index=rows, columns=[p.label for p in programs], dtype=float)
    for res in results:
        spending = {s.output:s.vals[0] for s in at.PlotData.programs(res, t_bins='all').series}
        for program in programs:
            df_programs.loc[res.name, program.label] = spending[program.name]

    # Populate emissions dataframe
    df_emissions = pd.DataFrame(index=rows, columns=emissions_pars)
    for res in results:
        emissions = {s.output:s.vals[0] for s in at.PlotData(res, outputs=emissions_pars, t_bins='all', time_aggregation='integrate').series}
        for k,v in emissions.items():
            df_emissions.at[res.name, k] = v
    df_emissions.columns = [name.replace('_', ' ').title() for name in df_emissions.columns]
    df_emissions['Additional CO2 reductions'] = 0

    # Populate outcomes (totals and co-benefits)
    df_outcomes = pd.DataFrame(index=rows, columns=['Total cost','Total emissions', 'Net emissions', 'Cost co-benefits','Other co-benefits'])
    for res in results:
        cost_cobenefit = 0
        additional_co2_reduction = 0
        other_cobenefits = []

        for program in programs:
            if res.model.program_instructions.alloc[program.name].interpolate(start_year):
                cost_cobenefit += cobenefits.at[program.name, 'Cost co-benefits']
                additional_co2_reduction += cobenefits.at[program.name, 'Additional annual CO2 reduction']
                if not pd.isna(cobenefits.at[program.name, 'Other co-benefits']):
                    other_cobenefits.append(cobenefits.at[program.name, 'Other co-benefits'])

        df_outcomes.loc[res.name, 'Cost co-benefits'] = cost_cobenefit
        df_outcomes.loc[res.name, 'Other co-benefits'] = ', '.join(other_cobenefits)

        # nb. Store the CO2 co-benefit in the emissions dataframe. It is multiplied by the simulation duration
        # to calculate a total value rather than annual value, and it is negative due to being a reduction
        df_emissions.loc[res.name, 'Additional CO2 reductions'] = -additional_co2_reduction*(res.t[-1]-res.t[0]) if additional_co2_reduction else 0

    # Add columns for total cost and emissions based on the other dataframes
    df_outcomes['Total cost'] = df_programs.sum(axis=1)
    df_outcomes['Net emissions'] = df_emissions.sum(axis=1)
    df_outcomes['Total emissions'] = df_outcomes['Net emissions']-df_emissions['Additional CO2 reductions']

    # Add extra header row to the dataframe
    tspan = f"({np.format_float_positional(res.t[0], trim='-')}-{np.format_float_positional(res.t[-1], trim='-')})"
    df_programs.columns = pd.MultiIndex.from_product([[f'Cost {tspan}']] + [df_programs.columns.values])
    df_emissions.columns = pd.MultiIndex.from_product([[f'Emissions {tspan}']] + [df_emissions.columns.values])
    df_outcomes.columns = pd.MultiIndex.from_product([[f'Outcomes {tspan}']] + [df_outcomes.columns.values])

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
                if val.startswith('Cost'):
                    color = "#fbb4ae"
                elif val.startswith("Emissions"):
                    color = " #b3cde3"
                elif val.startswith("Outcomes"):
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

        tspan = df.columns[0][0].split(' ')[1]
        cost_header = f'Cost {tspan}'
        for program in df[cost_header].columns:
            formats[df.columns.get_loc((cost_header, program)) + df.index.nlevels] = currency_format

        outcome_header = f'Outcomes {tspan}'
        for cost_col in [(outcome_header, 'Total cost'), (outcome_header, 'Cost co-benefits')]:
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

    ax.set_title('Budget allocation' + (f' {title_suffix}' if title_suffix else ''), fontsize=25)
    ax.set_xlabel(None)
    fig.tight_layout()
    return fig


def plot_emissions(df: pd.DataFrame, title_suffix:str=None, net_emissions=True) -> plt.Figure:
    """
    Plot a bar graph of emissions by category for each scenario

    :param df: A dataframe where the index has the name of the scenario, and the columns are names of emissions sources
    :param title_suffix: Optionally specify a suffix to append to the title
    :param net_emissions: If False, additional CO2 reductions will be shown as a separate bar below the other emissions
                        sources. The total height of the bar corresponds to all modelled emissions without accounting
                        for other CO2 reductions. If True, additional CO2 reductions will be applied as an offset to each
                        column of bars, so the total height of the bar group corresponds to net emissions.
                        - Total emissions is intended to convey the total emitted CO2 per source, with additional
                          CO2 co-benefits explicitly represented as a separate bar
                        - Net emissions is intended to convey the relative climate benefit of each scenario accounting
                          for additional CO2 reductions
                        Note that optimization is performed on the basis of net emissions, therefore it may be possible for
                        a scenario to have higher total emissions but still be preferable due to additional CO2 reductions.
                        The net emissions plot will show a lower bar for optimal scenarios, whereas the total emissions plot
                        may not. However, the net emissions plot may be counterintuitive to read if the additional CO2 reduction
                        is very large compared to other emissions sources - the top edge of the bar corresponds to the net
                        emissions for
    :return: A matplotlib Figure
    """

    font_size = 22

    cmap = mpl.colormaps['tab20']
    colors = cmap.colors[0::2]+cmap.colors[1::2]
    colors = [colors[i%len(colors)] for i in range(len(df.columns))][::-1]

    fig, ax = plt.subplots()

    if net_emissions:
        bottom = df['Additional CO2 reductions'].values
        df = df.drop(columns='Additional CO2 reductions')
        df.iloc[:, ::-1].plot.bar(stacked=True, color=colors[1:], ax=ax, fontsize=font_size, bottom=bottom)
    else:
        if not df['Additional CO2 reductions'].any():
            df = df.drop(columns='Additional CO2 reductions')
        df.iloc[:, ::-1].plot.bar(stacked=True, color=colors, ax=ax, fontsize=font_size)

        # Apply hatched pattern to "Additional CO2 reductions" bars
        for bar, label in zip(ax.patches, df.columns[::-1].repeat(df.shape[0])):
            if label == "Additional CO2 reductions":
                bar.set_hatch('//')  # Applying hatched pattern

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], title='Emission Sources', bbox_to_anchor=(1.0, 1.0), loc='upper left', fontsize=font_size - 2, title_fontsize=font_size)

    ax.yaxis.set_major_formatter(mpl.ticker.StrMethodFormatter('{x:,.0f}'))
    ax.set_xticklabels(df.index, ha='center', rotation=90)
    ax.set_xlabel(None)
    ax.set_ylabel('Emissions (CO2e)', fontsize=font_size)

    if net_emissions:
        ax.set_title("Net CO2e Emissions" + (f' {title_suffix}' if title_suffix else ''), fontsize=font_size + 2)
    else:
        ax.set_title("Total CO2e Emissions" + (f' {title_suffix}' if title_suffix else ''), fontsize=font_size + 2)

    if ((not net_emissions) and 'Additional CO2 reductions' in df.columns) or (net_emissions and bottom.min() < 0):
        ax.axhline(0, color='black', linewidth=0.5)
    else:
        ax.set_ylim(bottom=0)

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

    tspan = df.columns[0][0].split(' ')[1]
    if title_suffix:
        title_suffix = f'{tspan[1:-1]} ({title_suffix})'
    else:
        title_suffix = tspan[1:-1]

    # Allocation outputs
    alloc = df[f'Cost {tspan}']
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
    emissions = df[f'Emissions {tspan}']

    # Emissions plots
    fig = plot_emissions(emissions, title_suffix, net_emissions=True)
    file_name = f'figs/{prefix}_Net_Emissions_{facility_code}.png'
    fig.savefig(file_name, dpi=300)
    plt.close(fig)
    print(f'Net emissions bar plots saved: {file_name}')

    fig = plot_emissions(emissions, title_suffix, net_emissions=False)
    file_name = f'figs/{prefix}_Total_Emissions_{facility_code}.png'
    fig.savefig(file_name, dpi=300)
    plt.close(fig)
    print(f'Total emissions bar plots saved: {file_name}')

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
