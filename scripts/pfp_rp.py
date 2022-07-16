# standard modules
import collections
import copy
import datetime
import logging
import os
# 3rd party modules
import dateutil
import matplotlib.pyplot as plt
import numpy
import pandas
import pylab
# PFP modules
from scripts import constants as c
from scripts import pfp_gf
from scripts import pfp_gfSOLO
from scripts import pfp_gui
from scripts import pfp_io
from scripts import pfp_part
from scripts import pfp_ts
from scripts import pfp_utils

logger = logging.getLogger("pfp_log")

def CalculateET(ds):
    """
    Purpose:
     Calculate ET from Fe
    Usage:
     pfp_rp.CalculateET(ds)
      where ds is a data structure
    Side effects:
     Series to hold the ET data are created in ds.
    Author: PRI
    Date: June 2015
    """
    series_list = list(ds.series.keys())
    Fe_list = [item for item in series_list if "Fe" in item[0:2]]
    for label in Fe_list:
        Fe, flag, attr = pfp_utils.GetSeriesasMA(ds, label)
        ET = Fe/c.Lv
        attr["long_name"] = "Evapo-transpiration"
        attr["standard_name"] = "water_evapotranspiration_flux"
        attr["units"] = "kg/m^2/s"
        pfp_utils.CreateSeries(ds, label.replace("Fe","ET"), ET, flag, attr)

def CalculateNEE(ds, l6_info):
    """
    Purpose:
     Calculate NEE from observed Fc and observed/modeled ER.
     Input and output names are held in info["NetEcosystemExchange"].
    Usage:
     pfp_rp.CalculateNEE(cf,ds)
      where cf is a conbtrol file object
            ds is a data structure
    Side effects:
     Series to hold the NEE data are created in ds.
    Author: PRI
    Date: August 2014
    """
    if "NetEcosystemExchange" not in l6_info:
        return
    # make the L6 "description" attribute for the target variable
    descr_level = "description_" + ds.globalattributes["processing_level"]
    # get the Fsd threshold
    Fsd_threshold = float(pfp_utils.get_keyvaluefromcf(l6_info, ["Options"], "Fsd_threshold",
                                                       default=10))
    # get the incoming shortwave radiation
    Fsd, _, _ = pfp_utils.GetSeriesasMA(ds, "Fsd")
    for label in list(l6_info["NetEcosystemExchange"].keys()):
        if (("Fco2" not in l6_info["NetEcosystemExchange"][label]) and
            ("ER" not in l6_info["NetEcosystemExchange"][label])):
            continue
        Fc_label = l6_info["NetEcosystemExchange"][label]["Fco2"]
        ER_label = l6_info["NetEcosystemExchange"][label]["ER"]
        output_label = l6_info["NetEcosystemExchange"][label]["output"]
        if Fc_label not in list(ds.series.keys()):
            continue
        Fc, Fc_flag, Fc_attr = pfp_utils.GetSeriesasMA(ds, Fc_label)
        if ER_label not in list(ds.series.keys()):
            continue
        ER, ER_flag, _ = pfp_utils.GetSeriesasMA(ds, ER_label)
        # put the day time Fc into the NEE series
        index = numpy.ma.where(Fsd >= Fsd_threshold)[0]
        ds.series[output_label]["Data"][index] = Fc[index]
        ds.series[output_label]["Flag"][index] = Fc_flag[index]
        # put the night time ER into the NEE series
        index = numpy.ma.where(Fsd < Fsd_threshold)[0]
        ds.series[output_label]["Data"][index] = ER[index]
        ds.series[output_label]["Flag"][index] = ER_flag[index]
        # update the attributes
        attr = ds.series[output_label]["Attr"]
        attr["units"] = Fc_attr["units"]
        attr["long_name"] = "Net Ecosystem Exchange"
        tmp = " Calculated from " + Fc_label + " and " + ER_label
        pfp_utils.append_to_attribute(attr, {descr_level: tmp})
        attr["comment1"] = "Fsd threshold used was " + str(Fsd_threshold)
        ds.series[output_label]["Attr"] = attr
        l6_info["Summary"]["NetEcosystemExchange"].append(label)
    return

def CalculateNEP(ds, l6_info):
    """
    Purpose:
     Calculate NEP from NEE
    Usage:
     pfp_rp.CalculateNEP(ds, l6_info)
      where ds is a data structure
            l6_info is the dictionary returned by ParseL6ControlFile()
    Side effects:
     Series to hold the NEP data are created in ds.
    Author: PRI
    Date: May 2015
    """
    # make the L6 "description" attribute for the target variable
    descr_level = "description_" + ds.globalattributes["processing_level"]
    for nee_name in list(l6_info["NetEcosystemExchange"].keys()):
        nep_name = nee_name.replace("NEE", "NEP")
        nee, flag, attr = pfp_utils.GetSeriesasMA(ds, nee_name)
        nep = float(-1)*nee
        attr["long_name"] = "Net Ecosystem Productivity"
        pfp_utils.append_to_attribute(attr, {descr_level: "calculated as -1*" + nee_name})
        pfp_utils.CreateSeries(ds, nep_name, nep, flag, attr)
    return

def ERUsingLasslop(ds, l6_info):
    """
    Purpose:
    Usage:
    Side effects:
    Author: IMcH, PRI
    Date: Back in the day
    """
    if "ERUsingLasslop" not in l6_info:
        return
    msg = " Estimating ER using Lasslop"
    logger.info(msg)
    EcoResp(ds, l6_info, "ERUsingLasslop")
    for output in l6_info["ERUsingLasslop"]["outputs"]:
        if output in list(ds.series.keys()):
            source = l6_info["ERUsingLasslop"]["outputs"][output]["source"]
            l6_info["Summary"]["EcosystemRespiration"].append(source)
            merge = l6_info["EcosystemRespiration"][source]["MergeSeries"]["source"].split(",")
            l6_info["MergeSeries"]["standard"][source] = {"output": source,
                                                          "source": merge}
        else:
            msg = output + " not in data structure"
            logger.error("!!!!!")
            logger.error(msg)
            logger.error("!!!!!")
            raise RuntimeError(msg)
    return

def ERUsingLloydTaylor(ds, l6_info):
    """
    Purpose:
    Usage:
    Author: IMcH
    Date: April 2022
    """
    if "ERUsingLloydTaylor" not in l6_info:
        return
    msg = " Estimating ER using Lloyd-Taylor"
    logger.info(msg)
    EcoResp(ds, l6_info, "ERUsingLloydTaylor")
    for output in l6_info["ERUsingLloydTaylor"]["outputs"]:
        if output in list(ds.series.keys()):
            source = l6_info["ERUsingLloydTaylor"]["outputs"][output]["source"]
            l6_info["Summary"]["EcosystemRespiration"].append(source)
            merge = l6_info["EcosystemRespiration"][source]["MergeSeries"]["source"].split(",")
            l6_info["MergeSeries"]["standard"][source] = {"output": source,
                                                          "source": merge}
        else:
            msg = output + " not in data structure"
            logger.error("!!!!!")
            logger.error(msg)
            logger.error("!!!!!")
            raise RuntimeError(msg)
    return

def EcoResp(ds, l6_info, called_by):
    """
    Purpose:
    Estimate ecosystem respiration
    Args:
        * ds: PyFluxPro data structure (class)
        * l6_info: information derived from L6 control file (dict)
        * called_by: the routine that called the function (str)
    Kwargs:
        * mode: choice of whether to to use Lloyd Taylor os Lasslop methods to
          estimate respiration (str; options "LT" [Lloyd Taylor - default]
          and "LL" [Lasslop])
    Author: IMcH, PRI
    Date: August 2019
    """
    # get the time step
    ts = int(float(ds.globalattributes["time_step"]))
    # Get required configs dict
    iel = l6_info[called_by]
    outputs = iel["outputs"].keys()
    # Set dict to select day or night fitting of rb depending on mode
    partition_dict = {'ERUsingLasslop': {'day_night_mode':
                                         'day', 'day_rb_bool': True},
                      'ERUsingLloydTaylor': {'day_night_mode': 'night',
                                             'day_rb_bool': False}}
    er_mode = partition_dict[called_by]['day_night_mode']
    rb_mode = partition_dict[called_by]['day_rb_bool']
    # Set attributes for ER and plotting
    descr = {"ERUsingLasslop": "Ecosystem respiration modelled by Lasslop",
             "ERUsingLloydTaylor": "Ecosystem respiration modelled by Lloyd-Taylor"}
    descr_level = "description_" + ds.globalattributes["processing_level"]
    ER_attr = {"units": "umol/m^2/s", "long_name": "Ecosystem respiration",
               descr_level: descr[called_by], "statistic_type": "average"}
    ER_attr = pfp_utils.make_attribute_dictionary(attr=ER_attr)
    site_name = ds.globalattributes["site_name"]
    # set the figure number
    if len(plt.get_fignums()) == 0:
        fig_num = 0
    else:
        fig_num = plt.get_fignums()[-1]
    # open the Excel file for writing all outputs
    xl_name = iel["info"]["data_file_path"]
    xl_writer = pandas.ExcelWriter(xl_name, engine = "xlsxwriter")
    # loop over the series of outputs (usually one only)
    for output in outputs:
        # Make the filtered dataframe (fix this to allow gap-filled drivers)
        ustars_dict = {x.split("_")[-1]: float(ds.series["Fco2"]["Attr"][x])
                       for x in ds.series["Fco2"]["Attr"] if "ustar" in x}
        var_list = ["Fco2", "Ta", "Ts", "Fsd", "ustar", "VPD"]
        df = pandas.DataFrame({var: ds.series[var]["Data"] for var in var_list},
                              index = ds.series["DateTime"]["Data"])
        # IM original code causes Fco2 to be masked if any driver is gap filled
        #is_valid = numpy.tile(True, int(ds.globalattributes["nc_nrecs"]))
        #for this_var in df.columns: is_valid *= ds.series[this_var]["Flag"] == 0
        #df.loc[~is_valid, "Fco2"] = numpy.nan
        # 2022/4/22 PRI
        # set Fco2 to NaN if
        #  - any driver has a QC flag not ending in 0
        #  - Fco2 is gap filled (only use observations)
        is_valid = numpy.tile(True, int(ds.globalattributes["nc_nrecs"]))
        for this_var in ["Ta", "Ts", "Fsd", "ustar", "VPD"]:
            is_valid *= numpy.mod(ds.series[this_var]["Flag"], 10) == 0
        for this_var in ["Fco2"]:
            is_valid *= ds.series[this_var]["Flag"] == 0
        df.loc[~is_valid, "Fco2"] = numpy.nan

        for year in ustars_dict:
            df.loc[(df.index.year == int(year)) &
                   (df.ustar < ustars_dict[year]) &
                   (df.Fsd < 10), "Fco2"] = numpy.nan
        # Set the weighting of air and soil temperatures
        configs_dict = iel["outputs"][output]
        drivers = configs_dict["drivers"]
        weighting = configs_dict["weights_air_soil"]
        re_drivers = [x for x in drivers if x in ["Ta", "Ts"]]
        if len(re_drivers) == 1:
            if re_drivers[0] == "Ta": weighting = "air"
            if re_drivers[0] == "Ts": weighting = "soil"
        elif len(re_drivers) == 2:
            if len(weighting) == 1:
                weighting = "air"
            elif len(weighting) == 2:
                try:
                    weighting = [float(x) for x in weighting]
                except TypeError:
                    weighting = "air"
            else:
                weighting = "air"
        # Pass the dataframe to the respiration class and get the results
        ptc = pfp_part.partition(df, weights_air_soil = weighting, fit_daytime_rb = rb_mode,
                                 time_step=ts)
        params_df = ptc.estimate_parameters(mode = er_mode)
        ER = ptc.estimate_er_time_series(params_df)
        ER_flag = numpy.tile(30, len(ER))
        # Write to series
        drivers = iel["outputs"][output]["drivers"]
        ER_attr["comment1"] = "Drivers were {}".format(str(drivers))
        pfp_utils.CreateSeries(ds, output, ER, ER_flag, ER_attr)
        # Write to excel
        params_df.to_excel(xl_writer, output)
        xl_writer.save()
        # Do plotting
        startdate = str(ds.series["DateTime"]["Data"][0])
        enddate = str(ds.series["DateTime"]["Data"][-1])
        target = iel["outputs"][output]["target"]
        fig_num = fig_num + 1
        #title_snippet = (" ").join(descr[called_by].split(" ")[2:])
        #title = site_name+" : " + output + title_snippet
        title = site_name + ": " + descr[called_by]
        pd = rp_initplot(site_name=site_name, label=target,
                         fig_num=fig_num, title=title,
                         nDrivers=len(drivers),
                         startdate=str(startdate),
                         enddate=str(enddate))
        rp_plot(pd, ds, output, drivers, target, iel, called_by)

def ERUsingSOLO(main_gui, ds, l6_info, called_by):
    """
    Purpose:
     Estimate ER using SOLO.
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
    Mods:
     21/8/2017 - moved GetERFromFc from pfp_ls.l6qc() to individual
                 ER estimation routines to allow for multiple sources
                 of ER.
    """
    if called_by not in l6_info:
        return
    if l6_info[called_by]["info"]["call_mode"].lower() == "interactive":
        # call the ERUsingSOLO GUI
        pfp_gfSOLO.gfSOLO_gui(main_gui, ds, l6_info, called_by)
    else:
        # ["gui"] settings dictionary done in pfp_rp.ParseL6ControlFile()
        pfp_gfSOLO.gfSOLO_run(ds, l6_info, called_by)
    for output in l6_info[called_by]["outputs"]:
        if output in list(ds.series.keys()):
            source = l6_info[called_by]["outputs"][output]["source"]
            l6_info["Summary"]["EcosystemRespiration"].append(source)
            merge = l6_info["EcosystemRespiration"][source]["MergeSeries"]["source"].split(",")
            l6_info["MergeSeries"]["standard"][source] = {"output": source,
                                                          "source": merge}
        else:
            msg = output + " not in data structure"
            logger.error("!!!!!")
            logger.error(msg)
            logger.error("!!!!!")
            raise RuntimeError(msg)
    return

def GetERFromFco2(ds, l6_info):
    """
    Purpose:
     Get the observed ecosystem respiration from measurements of Fc by
     filtering out daytime periods.  Note that the removal of low tubulence
     periods has been done by pfp_ck.ApplyTurbulenceFilter() before this
     routine is called.
     The Fsd threshold for determining day time and night time and the
     ustar threshold are set in the [Params] section of the L5 control
     file.
     Re-write of the original penned in August 2014
    Usage:
     pfp_rp.GetERFromFco2(ds, l6_info)
     where ds is a data structure
           l6_info is the dictionary returned by ParseL6ControlFile()
    Side effects:
     A new series called "ER" is created in the data structure.
    Author: PRI
    Date: October 2015
    """
    nrecs = int(ds.globalattributes["nc_nrecs"])
    ER = {"Label": "ER"}
    # get the CO2 flux
    Fco2 = pfp_utils.GetVariable(ds, "Fco2")
    # check for missing data, CO2 flux should be gap filled by this point
    if numpy.any(numpy.ma.getmaskarray(Fco2["Data"])):
        msg = " CO2 flux Fco2 contains missing data, aborting L6 ..."
        logger.error("!!!!!")
        logger.error(msg)
        logger.error("!!!!!")
        raise RuntimeError(msg)
    # get a copy of the Fco2 flag and make the attribute dictionary
    ER["Flag"] = numpy.array(Fco2["Flag"])
    # make the ER attribute dictionary
    descr_level = "description_" + ds.globalattributes["processing_level"]
    ER["Attr"] = {"long_name": "Ecosystem respiration", "units": Fco2["Attr"]["units"],
                  descr_level: "Ecosystem respiration as nocturnal, ustar-filtered Fco2",
                  "statistic_type": "average"}
    for attr in ["valid_range", "height", "instrument"]:
        if attr in Fco2["Attr"]:
            ER["Attr"][attr] = Fco2["Attr"][attr]
    # only accept Fco2 with QC flag values of 0 or 10
    notok = numpy.ones(nrecs)
    for flag_value in [0, 10]:
        idx = numpy.where(Fco2["Flag"] == flag_value)[0]
        notok[idx] = numpy.int(0)
    Fco2["Data"] = numpy.ma.masked_where((notok == 1), Fco2["Data"])
    ER["Flag"] = numpy.where((notok == 1), numpy.full(nrecs, 501), numpy.zeros(nrecs))
    # get the indicator series
    daynight_indicator = get_daynight_indicator(ds, l6_info)
    idx = numpy.where(daynight_indicator["values"] == 0)[0]
    ER["Flag"][idx] = numpy.int32(502)
    # apply the filter to get ER from Fco2
    ER["Data"] = numpy.ma.masked_where(daynight_indicator["values"] == 0, Fco2["Data"], copy=True)
    for item in daynight_indicator["attr"]:
        ER["Attr"][item] = daynight_indicator["attr"][item]
    pfp_utils.CreateVariable(ds, ER)
    pc1 = int((100*float(numpy.ma.count(ER["Data"]))/float(len(idx))) + 0.5)
    pc2 = int((100*float(numpy.ma.count(ER["Data"]))/float(ER["Data"].size)) + 0.5)
    msg = " ER contains " + str(pc1) + "% of all nocturnal data ("
    msg += str(pc2) + "% of all data)"
    logger.info(msg)
    return

def L6_summary(ds, l6_info):
    """
    Purpose:
     Produce summaries of L6 data, write them to an Excel spreadsheet and plot them.
    Usage:
    Author: PRI
    Date: June 2015
    """
    logger.info(" Doing the L6 summary")
    # set up a dictionary of lists
    series_dict = L6_summary_createseriesdict(ds, l6_info)
    # open the Excel workbook
    out_name = os.path.join(l6_info["Files"]["file_path"],
                            l6_info["Files"]["out_filename"])
    xl_name = out_name.replace(".nc", "_Summary.xls")
    try:
        xl_file = pfp_io.xl_open_write(xl_name)
    except IOError:
        logger.error(" L6_summary: error opening Excel file "+xl_name)
        return 0
    # open the netCDF files for the summary results
    # all data as groups in one netCDF4 file
    nc_name = out_name.replace(".nc", "_Summary.nc")
    nc_summary = pfp_io.nc_open_write(nc_name, nctype='NETCDF4')
    pfp_io.nc_write_globalattributes(nc_summary, ds, flag_defs=False)
    # daily averages and totals, all variables
    daily_dict = L6_summary_daily(ds, series_dict)
    L6_summary_write_xlfile(xl_file, "Daily (all)", daily_dict)
    # combined netCDF summary file
    nc_group = nc_summary.createGroup("Daily")
    L6_summary_write_ncfile(nc_group, daily_dict)
    # separate daily file
    nc_daily = pfp_io.nc_open_write(out_name.replace(".nc", "_Daily.nc"))
    pfp_io.nc_write_globalattributes(nc_daily, daily_dict, flag_defs=False)
    L6_summary_write_ncfile(nc_daily, daily_dict)
    nc_daily.close()
    # daily averages and totals, CO2 and H2O fluxes only
    fluxes_dict = L6_summary_co2andh2o_fluxes(ds, series_dict, daily_dict)
    L6_summary_write_xlfile(xl_file, "Daily (CO2,H2O)", fluxes_dict)
    # monthly averages and totals
    monthly_dict = L6_summary_monthly(ds, series_dict)
    L6_summary_write_xlfile(xl_file, "Monthly", monthly_dict)
    # combined netCDF summary file
    nc_group = nc_summary.createGroup("Monthly")
    L6_summary_write_ncfile(nc_group, monthly_dict)
    # separate monthly file
    nc_monthly = pfp_io.nc_open_write(out_name.replace(".nc", "_Monthly.nc"))
    pfp_io.nc_write_globalattributes(nc_monthly, monthly_dict, flag_defs=False)
    L6_summary_write_ncfile(nc_monthly, monthly_dict)
    nc_monthly.close()
    # annual averages and totals
    annual_dict = L6_summary_annual(ds, series_dict)
    L6_summary_write_xlfile(xl_file, "Annual", annual_dict)
    # combined netCDF summary file
    nc_group = nc_summary.createGroup("Annual")
    L6_summary_write_ncfile(nc_group, annual_dict)
    # separate annual file
    nc_annual = pfp_io.nc_open_write(out_name.replace(".nc", "_Annual.nc"))
    pfp_io.nc_write_globalattributes(nc_annual, annual_dict, flag_defs=False)
    L6_summary_write_ncfile(nc_annual, annual_dict)
    nc_annual.close()
    # cumulative totals
    cumulative_dict = L6_summary_cumulative(ds, series_dict)
    years = sorted(list(cumulative_dict.keys()))
    for year in years:
        nrecs = len(cumulative_dict[year]["variables"]["DateTime"]["Data"])
        if nrecs < 65530:
            L6_summary_write_xlfile(xl_file, "Cumulative("+str(year)+")", cumulative_dict[str(year)])
        else:
            msg = "L6 cumulative: too many rows for .xls workbook, skipping "+year
            logger.warning(msg)
        nc_group = nc_summary.createGroup("Cumulative_"+str(year))
        L6_summary_write_ncfile(nc_group, cumulative_dict[str(year)])
    # close the summary netCDF file
    nc_summary.close()
    # separate cumulative file
    nc_cumulative = pfp_io.nc_open_write(out_name.replace(".nc", "_Cumulative.nc"))
    pfp_io.nc_write_globalattributes(nc_cumulative, cumulative_dict["all"], flag_defs=False)
    L6_summary_write_ncfile(nc_cumulative, cumulative_dict["all"])
    nc_cumulative.close()
    # close the Excel workbook
    xl_file.save(xl_name)
    # plot the daily averages and sums
    L6_summary_plotdaily(daily_dict, l6_info)
    # plot the cumulative sums
    L6_summary_plotcumulative(cumulative_dict, l6_info)

def L6_summary_plotdaily(daily_dict, l6_info):
    """
    Purpose:
     Plot the daily averages or sums with a 30 day filter.
    Usage:
     L6_summary_plotdaily(daily_dict)
     where daily_dict is the dictionary of results returned by L6_summary_daily
    Author: PRI
    Date: June 2015
    """
    ddv = daily_dict["variables"]
    type_list = []
    for item in list(ddv.keys()):
        if item[0:2] == "ER": type_list.append(item[2:])
    for item in type_list:
        if "NEE" + item not in ddv or "GPP" + item not in ddv:
            type_list.remove(item)
    # plot time series of NEE, GPP and ER
    sdate = ddv["DateTime"]["Data"][0].strftime("%d-%m-%Y")
    edate = ddv["DateTime"]["Data"][-1].strftime("%d-%m-%Y")
    site_name = l6_info["Global"]["site_name"]
    title_str = site_name+": "+sdate+" to "+edate
    for item in type_list:
        if l6_info["Options"]["call_mode"].lower()=="interactive":
            plt.ion()
        else:
            current_backend = plt.get_backend()
            plt.switch_backend("agg")
            plt.ioff()
        fig = plt.figure(figsize=(16,4))
        fig.canvas.manager.set_window_title("Carbon Budget: "+item.replace("_",""))
        plt.figtext(0.5,0.95,title_str,horizontalalignment='center')
        plt.plot(ddv["DateTime"]["Data"],ddv["NEE"+item]["Data"],'b-',alpha=0.3)
        plt.plot(ddv["DateTime"]["Data"],pfp_ts.smooth(ddv["NEE"+item]["Data"],window_len=30),
                 'b-',linewidth=2,label="NEE"+item+" (30 day filter)")
        plt.plot(ddv["DateTime"]["Data"],ddv["GPP"+item]["Data"],'g-',alpha=0.3)
        plt.plot(ddv["DateTime"]["Data"],pfp_ts.smooth(ddv["GPP"+item]["Data"],window_len=30),
                 'g-',linewidth=2,label="GPP"+item+" (30 day filter)")
        plt.plot(ddv["DateTime"]["Data"],ddv["ER"+item]["Data"],'r-',alpha=0.3)
        plt.plot(ddv["DateTime"]["Data"],pfp_ts.smooth(ddv["ER"+item]["Data"],window_len=30),
                 'r-',linewidth=2,label="ER"+item+" (30 day filter)")
        plt.axhline(0)
        plt.xlabel("Date")
        plt.ylabel(ddv["NEE"+item]["Attr"]["units"])
        plt.legend(loc='upper left',prop={'size':8})
        plt.tight_layout()
        sdt = ddv["DateTime"]["Data"][0].strftime("%Y%m%d")
        edt = ddv["DateTime"]["Data"][-1].strftime("%Y%m%d")
        plot_path = pfp_utils.get_keyvaluefromcf(l6_info, ["Files"], "plot_path", default="plots/")
        plot_path = os.path.join(plot_path, "L6", "")
        if not os.path.exists(plot_path): os.makedirs(plot_path)
        figure_name = site_name.replace(" ","")+"_CarbonBudget"+item+"_"+sdt+"_"+edt+'.png'
        figure_path = os.path.join(plot_path, figure_name)
        fig.savefig(figure_path, format='png')
        if l6_info["Options"]["call_mode"].lower() == "interactive":
            plt.draw()
            pfp_utils.mypause(0.5)
            plt.ioff()
        else:
            plt.close(fig)
            plt.switch_backend(current_backend)
            plt.ion()
    # plot time series of Fn,Fg,Fh,Fe
    if l6_info["Options"]["call_mode"].lower() == "interactive":
        plt.ion()
    else:
        current_backend = plt.get_backend()
        plt.switch_backend("agg")
        plt.ioff()
    fig = plt.figure(figsize=(16,4))
    fig.canvas.manager.set_window_title("Surface Energy Budget")
    plt.figtext(0.5,0.95,title_str,horizontalalignment='center')
    for label, line in zip(["Fn", "Fg", "Fh", "Fe"], ["k-", "g-", "r-", "b-"]):
        if label in daily_dict["variables"]:
            plt.plot(ddv["DateTime"]["Data"], ddv[label]["Data"], line, alpha=0.3)
            plt.plot(ddv["DateTime"]["Data"], pfp_ts.smooth(ddv[label]["Data"], window_len=30),
                     line, linewidth=2, label=label+" (30 day filter)")
    plt.xlabel("Date")
    plt.ylabel(ddv["Fn"]["Attr"]["units"])
    plt.legend(loc='upper left',prop={'size':8})
    plt.tight_layout()
    sdt = ddv["DateTime"]["Data"][0].strftime("%Y%m%d")
    edt = ddv["DateTime"]["Data"][-1].strftime("%Y%m%d")
    plot_path = pfp_utils.get_keyvaluefromcf(l6_info, ["Files"], "plot_path", default="plots/")
    plot_path = os.path.join(plot_path, "L6", "")
    if not os.path.exists(plot_path): os.makedirs(plot_path)
    figname = plot_path+site_name.replace(" ","")+"_SEB"
    figname = figname+"_"+sdt+"_"+edt+'.png'
    fig.savefig(figname,format='png')
    if l6_info["Options"]["call_mode"].lower()=="interactive":
        plt.draw()
        pfp_utils.mypause(0.5)
        plt.ioff()
    else:
        plt.close(fig)
        plt.switch_backend(current_backend)
        plt.ion()

def L6_summary_plotcumulative(cumulative_dict, l6_info):
    # cumulative plots
    color_list = ["blue","red","green","yellow","magenta","black","cyan","brown"]
    year_list = [y for y in list(cumulative_dict.keys()) if y not in ["all"]]
    year_list.sort()
    cdy0 = cumulative_dict[year_list[0]]
    type_list = []
    for item in list(cdy0["variables"].keys()):
        if item[0:2] == "ER": type_list.append(item[2:])
    for item in type_list:
        if "NEE"+item not in cdy0["variables"] or "GPP"+item not in cdy0["variables"]:
            type_list.remove(item)
    # do the plots
    site_name = l6_info["Global"]["site_name"]
    title_str = site_name+": "+year_list[0]+" to "+year_list[-1]
    # get lists of X labels (letter of month) and position
    xlabels = numpy.array(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    xlabel_posn = numpy.array([0,31, 59, 89, 120, 150, 181, 212, 242, 273, 303, 334])/float(366)
    for item in type_list:
        if l6_info["Options"]["call_mode"].lower() == "interactive":
            plt.ion()
        else:
            current_backend = plt.get_backend()
            plt.switch_backend("agg")
            plt.ioff()
        fig = plt.figure(figsize=(8,8))
        fig.canvas.manager.set_window_title("Cumulative plots: "+item.replace("_",""))
        plt.suptitle(title_str)
        plt.subplot(221)
        plt.title("NEE: "+item.replace("_",""),fontsize=12)
        for n,year in enumerate(year_list):
            cdyv = cumulative_dict[year]["variables"]
            cdyt = cdyv["DateTime"]["Data"]
            cyf = [pfp_utils.get_yearfractionfromdatetime(dt) - int(year) for dt in cdyt]
            plt.plot(cyf, cdyv["NEE"+item]["Data"], color=color_list[numpy.mod(n,8)],
                     label=str(year))
        plt.xlim([0, 1])
        pylab.xticks(xlabel_posn, xlabels)
        plt.xlabel("Month")
        plt.ylabel(cdyv["NEE"+item]["Attr"]["units"])
        plt.legend(loc='lower left',prop={'size':8})

        plt.subplot(222)
        plt.title("GPP: "+item.replace("_",""),fontsize=12)
        for n,year in enumerate(year_list):
            cdyv = cumulative_dict[year]["variables"]
            cdyt = cdyv["DateTime"]["Data"]
            cyf = [pfp_utils.get_yearfractionfromdatetime(dt) - int(year) for dt in cdyt]
            plt.plot(cyf, cdyv["GPP"+item]["Data"],color=color_list[numpy.mod(n,8)],
                     label=str(year))
        plt.xlim([0, 1])
        pylab.xticks(xlabel_posn, xlabels)
        plt.xlabel("Month")
        plt.ylabel(cdyv["GPP"+item]["Attr"]["units"])
        plt.legend(loc='lower right',prop={'size':8})

        plt.subplot(223)
        plt.title("ER: "+item.replace("_",""),fontsize=12)
        for n,year in enumerate(year_list):
            cdyv = cumulative_dict[year]["variables"]
            cdyt = cdyv["DateTime"]["Data"]
            cyf = [pfp_utils.get_yearfractionfromdatetime(dt) - int(year) for dt in cdyt]
            plt.plot(cyf, cdyv["ER"+item]["Data"],color=color_list[numpy.mod(n,8)],
                     label=str(year))
        plt.xlim([0, 1])
        pylab.xticks(xlabel_posn, xlabels)
        plt.xlabel("Month")
        plt.ylabel(cdyv["ER"+item]["Attr"]["units"])
        plt.legend(loc='lower right',prop={'size':8})

        plt.subplot(224)
        plt.title("ET & Precip",fontsize=12)
        for n,year in enumerate(year_list):
            cdyv = cumulative_dict[year]["variables"]
            cdyt = cdyv["DateTime"]["Data"]
            cyf = [pfp_utils.get_yearfractionfromdatetime(dt) - int(year) for dt in cdyt]
            plt.plot(cyf, cdyv["ET"]["Data"],color=color_list[numpy.mod(n,8)],
                     label=str(year))
            plt.plot(cyf, cdyv["Precip"]["Data"],color=color_list[numpy.mod(n,8)],
                     linestyle='--')
        plt.xlim([0, 1])
        pylab.xticks(xlabel_posn, xlabels)
        plt.xlabel("Month")
        plt.ylabel(cdyv["ET"]["Attr"]["units"])
        plt.legend(loc='upper left',prop={'size':8})
        plt.tight_layout(rect=[0, 0, 1, 0.98])
        # save a hard copy of the plot
        sdt = year_list[0]
        edt = year_list[-1]
        plot_path = pfp_utils.get_keyvaluefromcf(l6_info, ["Files"], "plot_path", default="plots/")
        plot_path = os.path.join(plot_path, "L6", "")
        if not os.path.exists(plot_path):
            os.makedirs(plot_path)
        figure_name = site_name.replace(" ", "")+"_Cumulative"+item+"_"+sdt+"_"+edt+'.png'
        figure_path = os.path.join(plot_path, figure_name)
        fig.savefig(figure_path, format='png')
        if l6_info["Options"]["call_mode"].lower() == "interactive":
            plt.draw()
            pfp_utils.mypause(0.5)
            plt.ioff()
        else:
            plt.close(fig)
            plt.switch_backend(current_backend)
            plt.ion()

def L6_summary_createseriesdict(ds, l6_info):
    """
    Purpose:
     Create a dictionary containing lists of variables, operators and formats
    for use by the daily, annual and cumulative routines.
    Usage:
     series_dict = L6_summary_createseriesdict(ds, l6_info)
     where ds is an OzFluxQC data structure
           l6_info is thye L6 information dictionary from ParseL6ControlFile()
           series_dict is a dictionary of various variable lists
    Author: PRI
    Date: June 2015
    """
    l6is = l6_info["Summary"]
    # create a dictionary to hold the data being summarised
    series_dict = {"daily":{},"annual":{},"cumulative":{},"lists":{}}
    sdl = series_dict["lists"]
    sdl["nee"] = [item for item in l6is["NetEcosystemExchange"]
                  if "NEE" in item[0:3] and item in list(ds.series.keys())]
    sdl["gpp"] = [item for item in l6is["GrossPrimaryProductivity"]
                  if "GPP" in item[0:3] and item in list(ds.series.keys())]
    sdl["er"] = [item for item in l6is["EcosystemRespiration"]
                  if "ER" in item[0:2] and item in list(ds.series.keys())]
    sdl["nep"] = [item.replace("NEE","NEP") for item in sdl["nee"]]
    sdl["nep"] = [item for item in sdl["nep"] if item in list(ds.series.keys())]
    sdl["co2"] = sdl["nee"]+sdl["nep"]+sdl["gpp"]+sdl["er"]
    for item in sdl["co2"]:
        series_dict["daily"][item] = {}
        series_dict["cumulative"][item] = {}
        series_dict["daily"][item]["operator"] = "sum"
        series_dict["daily"][item]["format"] = "0.00"
        series_dict["cumulative"][item]["operator"] = "sum"
        series_dict["cumulative"][item]["format"] = "0.00"
    sdl["ET"] = [item for item in list(ds.series.keys()) if "ET" in item[0:2]]
    sdl["Precip"] = [item for item in list(ds.series.keys()) if "Precip" in item[0:6]]
    sdl["h2o"] = sdl["ET"]+sdl["Precip"]
    for item in sdl["h2o"]:
        series_dict["daily"][item] = {"operator":"sum","format":"0.00"}
        series_dict["cumulative"][item] = {"operator":"sum","format":"0.00"}
    if "AH" in list(ds.series.keys()):
        series_dict["daily"]["AH"] = {"operator":"average","format":"0.00"}
    if "CO2" in list(ds.series.keys()):
        series_dict["daily"]["CO2"] = {"operator":"average","format":"0.0"}
    if "Fco2" in list(ds.series.keys()):
        series_dict["daily"]["Fco2"] = {"operator":"average","format":"0.00"}
    if "Fe" in list(ds.series.keys()):
        series_dict["daily"]["Fe"] = {"operator":"average","format":"0.0"}
    if "Fh" in list(ds.series.keys()):
        series_dict["daily"]["Fh"] = {"operator":"average","format":"0.0"}
    if "Fg" in list(ds.series.keys()):
        series_dict["daily"]["Fg"] = {"operator":"average","format":"0.0"}
    if "Fn" in list(ds.series.keys()):
        series_dict["daily"]["Fn"] = {"operator":"average","format":"0.0"}
    if "Fsd" in list(ds.series.keys()):
        series_dict["daily"]["Fsd"] = {"operator":"average","format":"0.0"}
    if "Fsu" in list(ds.series.keys()):
        series_dict["daily"]["Fsu"] = {"operator":"average","format":"0.0"}
    if "Fld" in list(ds.series.keys()):
        series_dict["daily"]["Fld"] = {"operator":"average","format":"0.0"}
    if "Flu" in list(ds.series.keys()):
        series_dict["daily"]["Flu"] = {"operator":"average","format":"0.0"}
    if "ps" in list(ds.series.keys()):
        series_dict["daily"]["ps"] = {"operator":"average","format":"0.00"}
    if "RH" in list(ds.series.keys()):
        series_dict["daily"]["RH"] = {"operator":"average","format":"0"}
    if "SH" in list(ds.series.keys()):
        series_dict["daily"]["SH"] = {"operator":"average","format":"0.0000"}
    if "Sws" in list(ds.series.keys()):
        series_dict["daily"]["Sws"] = {"operator":"average","format":"0.000"}
    if "Ta" in list(ds.series.keys()):
        series_dict["daily"]["Ta"] = {"operator":"average","format":"0.00"}
    if "Ts" in list(ds.series.keys()):
        series_dict["daily"]["Ts"] = {"operator":"average","format":"0.00"}
    if "ustar" in list(ds.series.keys()):
        series_dict["daily"]["ustar"] = {"operator":"average","format":"0.00"}
    if "VP" in list(ds.series.keys()):
        series_dict["daily"]["VP"] = {"operator":"average","format":"0.000"}
    if "Ws" in list(ds.series.keys()):
        series_dict["daily"]["Ws"] = {"operator":"average","format":"0.00"}
    series_dict["annual"] = series_dict["daily"]
    series_dict["monthly"] = series_dict["daily"]
    return series_dict

def L6_summary_daily(ds, series_dict):
    """
    Purpose:
     Calculate the daily averages or sums of various quantities and write
     them to a worksheet in an Excel workbook.
    Usage:
     L6_summary_daily(ds, series_dict)
     where ds is an OzFluxQC data structure
           series_dict is a dictionary of various variable lists
    Author: PRI
    Date: June 2015
    """
    logger.info(" Doing the daily summary (data) at L6")
    dt = ds.series["DateTime"]["Data"]
    ts = int(float(ds.globalattributes["time_step"]))
    si = pfp_utils.GetDateIndex(dt,str(dt[0]),ts=ts,default=0,match="startnextday")
    ei = pfp_utils.GetDateIndex(dt,str(dt[-1]),ts=ts,default=len(dt)-1,match="endpreviousday")
    ldt = dt[si:ei+1]
    ntsInDay = int(24.0*60.0/float(ts))
    nDays = int(len(ldt))//ntsInDay
    # create an empty data array and an array of zeros for the flag
    f0 = numpy.zeros(nDays, dtype=numpy.int32)
    ldt_daily = [ldt[0]+datetime.timedelta(days=i) for i in range(0,nDays)]
    # create a dictionary to hold the daily statistics
    daily_dict = {"globalattributes": copy.deepcopy(ds.globalattributes),
                  "variables":{}}
    ddg = daily_dict["globalattributes"]
    ddv = daily_dict["variables"]
    # create the datetime variable
    ddv["DateTime"] = {"Data": ldt_daily, "Flag": f0,
                       "Attr":{"units": "Days", "format": "dd/mm/yyyy", "time_step": "daily"}}
    ddg["nc_nrecs"] = len(ldt_daily)
    ddg["time_step"] = "daily"
    series_list = list(series_dict["daily"].keys())
    series_list.sort()
    for item in series_list:
        if item not in list(ds.series.keys()):
            continue
        ddv[item] = {"Data": [], "Attr": {}}
        variable = pfp_utils.GetVariable(ds, item, start=si, end=ei)
        if item in series_dict["lists"]["co2"]:
            variable = pfp_utils.convert_units_func(ds, variable, "gC/m^2")
            ddv[item]["Attr"]["units"] = "gC/m^2"
        elif item in series_dict["lists"]["ET"]:
            variable = pfp_utils.convert_units_func(ds, variable, "kg/m^2")
            ddv[item]["Attr"]["units"] = "kg/m^2"
        else:
            ddv[item]["Attr"]["units"] = variable["Attr"]["units"]
        data_2d = variable["Data"].reshape(nDays, ntsInDay)
        if series_dict["daily"][item]["operator"].lower() == "average":
            ddv[item]["Data"] = numpy.ma.average(data_2d, axis=1)
        elif series_dict["daily"][item]["operator"].lower() == "sum":
            ddv[item]["Data"] = numpy.ma.sum(data_2d, axis=1)
            ddv[item]["Attr"]["units"] = ddv[item]["Attr"]["units"]+"/day"
        else:
            msg = "Unrecognised operator (" + series_dict["daily"][item]["operator"]
            msg = msg + ") for series " + item
            logger.error(msg)
            continue
        # add the format to be used
        ddv[item]["Attr"]["format"] = series_dict["daily"][item]["format"]
        # copy some of the variable attributes
        default_list = ["long_name", "height", "instrument"]
        descr_list = [d for d in list(variable["Attr"].keys()) if "description" in d]
        vattr_list = default_list + descr_list
        for attr in vattr_list:
            if attr in variable["Attr"]:
                ddv[item]["Attr"][attr] = variable["Attr"][attr]
        # now do the flag, this is the fraction of data with QC flag = 0 in the day
        ddv[item]["Flag"] = numpy.zeros(nDays, dtype=numpy.float64)
        flag_2d = variable["Flag"].reshape(nDays, ntsInDay)
        for i in range(nDays):
            ddv[item]["Flag"][i] = 1-float(numpy.count_nonzero(flag_2d[i,:]))/float(ntsInDay)
    return daily_dict

def L6_summary_co2andh2o_fluxes(ds, series_dict, daily_dict):
    """
    Purpose:
    Usage:
    Author: PRI
    Date: March 2016
    """
    logger.info(" Doing the daily summary (fluxes) at L6")
    sdl = series_dict["lists"]
    series_list = sdl["h2o"]+sdl["co2"]
    fluxes_dict = {"globalattributes":copy.deepcopy(daily_dict["globalattributes"]),
                   "variables":{}}
    # create the datetime variable
    fluxes_dict["variables"]["DateTime"] = daily_dict["variables"]["DateTime"]
    for item in series_list:
        fluxes_dict["variables"][item] = {}
        fluxes_dict["variables"][item]["Data"] = daily_dict["variables"][item]["Data"]
        fluxes_dict["variables"][item]["Attr"] = daily_dict["variables"][item]["Attr"]
        fluxes_dict["variables"][item+"_Flag"] = {}
        fluxes_dict["variables"][item+"_Flag"]["Data"] = daily_dict["variables"][item]["Flag"]
        fluxes_dict["variables"][item+"_Flag"]["Attr"] = {"units":"1","format":"0.00"}
    return fluxes_dict

def L6_summary_write_ncfile(nc_obj, data_dict):
    """
    Purpose:
     Write the L6 summary statistics (daily, monthly, annual and cumulative)
     to a single netCDF file with different groups for each time period.
    Usage:
    Author: PRI
    Date: January 2018
    """
    # write the data to the group
    dt = data_dict["variables"]["DateTime"]["Data"]
    nrecs = len(dt)
    # and give it dimensions of time, latitude and longitude
    nc_obj.createDimension("time", nrecs)
    nc_obj.createDimension("latitude", 1)
    nc_obj.createDimension("longitude", 1)
    dims = ("time", "latitude", "longitude")
    # write the time variable to the netCDF object
    nc_time_units = "days since 1800-01-01 00:00:00.0"
    nc_time = pfp_utils.get_nctime_from_datetime_data(dt, nc_time_units=nc_time_units)
    nc_var = nc_obj.createVariable("time", "d", ("time",))
    nc_var[:] = nc_time
    nc_var.setncattr("long_name", "time")
    nc_var.setncattr("standard_name", "time")
    nc_var.setncattr("units", nc_time_units)
    # write the latitude and longitude variables to the group
    nc_var = nc_obj.createVariable("latitude", "d", ("latitude",))
    nc_var[:] = float(data_dict["globalattributes"]["latitude"])
    nc_var.setncattr('long_name', 'latitude')
    nc_var.setncattr('standard_name', 'latitude')
    nc_var.setncattr('units', 'degrees north')
    nc_var = nc_obj.createVariable("longitude", "d", ("longitude",))
    nc_var[:] = float(data_dict["globalattributes"]["longitude"])
    nc_var.setncattr('long_name', 'longitude')
    nc_var.setncattr('standard_name', 'longitude')
    nc_var.setncattr('units', 'degrees east')
    # get a list of variables to write to the netCDF file
    labels = sorted([label for label in list(data_dict["variables"].keys()) if label != "DateTime"])
    # write the variables to the netCDF file object
    for label in labels:
        nc_var = nc_obj.createVariable(label, "d", dims)
        nc_var[:, 0, 0] = data_dict["variables"][label]["Data"].tolist()
        for attr_key in data_dict["variables"][label]["Attr"]:
            if attr_key not in ["format"]:
                attr_value = data_dict["variables"][label]["Attr"][attr_key]
                nc_var.setncattr(attr_key, attr_value)
    return

def L6_summary_write_xlfile(xl_file,sheet_name,data_dict):
    # add the daily worksheet to the summary Excel file
    xl_sheet = xl_file.add_sheet(sheet_name)
    pfp_io.xl_write_data(xl_sheet,data_dict["variables"])

def L6_summary_monthly(ds,series_dict):
    """
    Purpose:
     Calculate the monthly averages or sums of various quantities and write
     them to a worksheet in an Excel workbook.
    Usage:
     L6_summary_monthly(ds,series_dict)
     where ds is an OzFluxQC data structure
           series_dict is a dictionary of various variable lists
    Author: PRI
    Date: July 2015
    """
    logger.info(" Doing the monthly summaries at L6")
    dt = ds.series["DateTime"]["Data"]
    ts = int(float(ds.globalattributes["time_step"]))
    si = pfp_utils.GetDateIndex(dt, str(dt[0]), ts=ts, default=0, match="startnextmonth")
    ldt = dt[si:]
    monthly_dict = {"globalattributes": copy.deepcopy(ds.globalattributes),
                    "variables": {}}
    mdg = monthly_dict["globalattributes"]
    mdv = monthly_dict["variables"]
    mdg["time_step"] = "monthly"
    mdv["DateTime"] = {"Data":numpy.ma.array([]),
                       "Flag":numpy.array([]),
                       "Attr":{"units":"Months", "format":"dd/mm/yyyy", "time_step":"Monthly"}}
    # create arrays in monthly_dict
    series_list = list(series_dict["monthly"].keys())
    series_list.sort()
    # create the data arrays
    for item in series_list:
        mdv[item] = {"Data":numpy.ma.array([]),
                     "Flag":numpy.array([]),
                     "Attr":{"units":'',"format":''}}
    # loop over the months in the data file
    start_date = ldt[0]
    end_date = start_date+dateutil.relativedelta.relativedelta(months=1)
    end_date = end_date-dateutil.relativedelta.relativedelta(minutes=ts)
    last_date = ldt[-1]
    while start_date<=last_date:
        # *** The Elise Pendall bug fix ***
        si = pfp_utils.GetDateIndex(dt, str(start_date), ts=ts, default=0)
        ei = pfp_utils.GetDateIndex(dt, str(end_date), ts=ts, default=len(dt)-1)
        mdv["DateTime"]["Data"] = numpy.append(mdv["DateTime"]["Data"], dt[si])
        for item in series_list:
            if item not in list(ds.series.keys()): continue
            variable = pfp_utils.GetVariable(ds, item, start=si, end=ei)
            if item in series_dict["lists"]["co2"]:
                variable = pfp_utils.convert_units_func(ds, variable, "gC/m^2")
                mdv[item]["Attr"]["units"] = "gC/m^2"
            elif item in series_dict["lists"]["ET"]:
                variable = pfp_utils.convert_units_func(ds, variable, "kg/m^2")
                mdv[item]["Attr"]["units"] = "kg/m^2"
            else:
                mdv[item]["Attr"]["units"] = variable["Attr"]["units"]
            if series_dict["monthly"][item]["operator"].lower() == "average":
                val = numpy.ma.average(variable["Data"])
                mdv[item]["Data"] = numpy.append(mdv[item]["Data"], val)
            elif series_dict["monthly"][item]["operator"].lower()=="sum":
                val = numpy.ma.sum(variable["Data"])
                mdv[item]["Data"] = numpy.append(mdv[item]["Data"], val)
                mdv[item]["Attr"]["units"] = mdv[item]["Attr"]["units"] + "/month"
            else:
                msg = "L6_summary_monthly: unrecognised operator"
                logger.error(msg)
            mdv[item]["Attr"]["format"] = series_dict["monthly"][item]["format"]
            # copy some of the variable attributes
            default_list = ["long_name", "height", "instrument"]
            descr_list = [d for d in list(variable["Attr"].keys()) if "description" in d]
            vattr_list = default_list + descr_list
            for attr in vattr_list:
                if attr in variable["Attr"]:
                    mdv[item]["Attr"][attr] = variable["Attr"][attr]
        start_date = end_date+dateutil.relativedelta.relativedelta(minutes=ts)
        end_date = start_date+dateutil.relativedelta.relativedelta(months=1)
        end_date = end_date-dateutil.relativedelta.relativedelta(minutes=ts)
    mdg["nc_nrecs"] = len(mdv["DateTime"]["Data"])
    return monthly_dict

def L6_summary_annual(ds, series_dict):
    """
    Purpose:
     Calculate the annual averages or sums of various quantities and write
     them to a worksheet in an Excel workbook.
    Usage:
     L6_summary_annual(ds,series_dict)
     where ds is an OzFluxQC data structure
           series_dict is a dictionary of various variable lists
    Author: PRI
    Date: June 2015
    """
    logger.info(" Doing the annual summaries at L6")
    dt = ds.series["DateTime"]["Data"]
    ts = int(float(ds.globalattributes["time_step"]))
    nperDay = int(24/(float(ts)/60.0)+0.5)
    si = pfp_utils.GetDateIndex(dt, str(dt[0]), ts=ts, default=0, match="startnextday")
    ei = pfp_utils.GetDateIndex(dt, str(dt[-1]), ts=ts, default=len(dt)-1, match="endpreviousday")
    ldt = dt[si:ei+1]
    start_year = ldt[0].year
    end_year = ldt[-1].year
    year_list = list(range(start_year, end_year+1, 1))
    nYears = len(year_list)
    annual_dict = {"globalattributes": copy.deepcopy(ds.globalattributes), "variables": {}}
    adg = annual_dict["globalattributes"]
    adv = annual_dict["variables"]
    adg["time_step"] = "annual"
    # copy the global attributes
    adv["DateTime"] = {"Data": [datetime.datetime(yr, 1, 1) for yr in year_list],
                       "Flag": numpy.zeros(nYears, dtype=numpy.int32),
                       "Attr": {"units": "Years", "format": "dd/mm/yyyy", "time_step": "Annual"}}
    adv["nDays"] = {"Data": numpy.full(nYears, c.missing_value, dtype=numpy.float64),
                    "Flag": numpy.zeros(nYears, dtype=numpy.int32),
                    "Attr": {"units": "Number of days","format": "0"}}
    # create arrays in annual_dict
    series_list = list(series_dict["annual"].keys())
    series_list.sort()
    for item in series_list:
        adv[item] = {"Data": numpy.ma.array([float(-9999)]*len(year_list)),
                     "Flag": numpy.zeros(nYears, dtype=numpy.int32),
                     "Attr": {"units": "Number of days","format": "0"}}
    for i, year in enumerate(year_list):
        if ts == 30:
            start_date = str(year) + "-01-01 00:30"
        elif ts == 60:
            start_date = str(year) + "-01-01 01:00"
        end_date = str(year+1) + "-01-01 00:00"
        si = pfp_utils.GetDateIndex(dt, start_date, ts=ts, default=0)
        ei = pfp_utils.GetDateIndex(dt, end_date, ts=ts, default=len(dt)-1)
        nDays = int((ei-si+1)/nperDay+0.5)
        adv["nDays"]["Data"][i] = nDays
        for item in series_list:
            if item not in list(ds.series.keys()):
                continue
            variable = pfp_utils.GetVariable(ds, item, start=si, end=ei)
            if item in series_dict["lists"]["co2"]:
                variable = pfp_utils.convert_units_func(ds, variable, "gC/m^2")
                adv[item]["Attr"]["units"] = "gC/m^2"
            elif item in series_dict["lists"]["ET"]:
                variable = pfp_utils.convert_units_func(ds, variable, "kg/m^2")
                adv[item]["Attr"]["units"] = "kg/m^2"
            else:
                adv[item]["Attr"]["units"] = variable["Attr"]["units"]
            if series_dict["annual"][item]["operator"].lower()=="average":
                adv[item]["Data"][i] = numpy.ma.average(variable["Data"])
            elif series_dict["annual"][item]["operator"].lower()=="sum":
                adv[item]["Data"][i] = numpy.ma.sum(variable["Data"])
                adv[item]["Attr"]["units"] = adv[item]["Attr"]["units"]+"/year"
            else:
                msg = "L6_summary_annual: unrecognised operator"
                logger.error(msg)
            adv[item]["Attr"]["format"] = series_dict["annual"][item]["format"]
            # copy some of the variable attributes
            default_list = ["long_name", "height", "instrument"]
            descr_list = [d for d in list(variable["Attr"].keys()) if "description" in d]
            vattr_list = default_list + descr_list
            for attr in vattr_list:
                if attr in variable["Attr"]:
                    adv[item]["Attr"][attr] = variable["Attr"][attr]
    adg["nc_nrecs"] = len(adv["DateTime"]["Data"])
    return annual_dict

def L6_summary_cumulative(ds, series_dict):
    """
    Purpose:
     Calculate the cumulative sums of various quantities and write
     them to a worksheet in an Excel workbook.
    Usage:
     L6_summary_cumulative(xl_file,ds,series_dict)
     where xl_file is an Excel file object
           ds is an OzFluxQC data structure
           series_dict is a dictionary of various variable lists
    Author: PRI
    Date: June 2015
    """
    logger.info(" Doing the cumulative summaries at L6")
    # get the datetime series and the time step
    dt = pfp_utils.GetVariable(ds, "DateTime")
    ts = int(float(ds.globalattributes["time_step"]))
    nrecs = int(ds.globalattributes["nc_nrecs"])
    # subtract 1 time step from the datetime to avoid orphan years
    cdt = dt["Data"] - datetime.timedelta(minutes=ts)
    years = sorted(list(set([ldt.year for ldt in cdt])))
    series_list = list(series_dict["cumulative"].keys())
    cumulative_dict = {}
    for year in years:
        cumulative_dict[str(year)] = cdyr = {"globalattributes":{}, "variables":{}}
        # copy the global attributes
        cdyr["globalattributes"] = copy.deepcopy(ds.globalattributes)
        start_date = datetime.datetime(year, 1, 1, 0, 0, 0) + datetime.timedelta(minutes=ts)
        end_date = datetime.datetime(year+1, 1, 1, 0, 0, 0)
        si = pfp_utils.GetDateIndex(dt["Data"], start_date, ts=ts, default=0)
        ei = pfp_utils.GetDateIndex(dt["Data"], end_date, ts=ts, default=nrecs-1)
        ldt = dt["Data"][si:ei+1]
        f0 = numpy.zeros(len(ldt), dtype=numpy.int32)
        cdyr["variables"]["DateTime"] = {"Data":ldt, "Flag":f0,
                                         "Attr":{"units":"Year", "format":"dd/mm/yyyy HH:MM",
                                                 "time_step":str(ts)}}
        for item in series_list:
            cdyr["variables"][item] = {"Data":[], "Attr":{}}
            variable = pfp_utils.GetVariable(ds, item, start=si, end=ei)
            if item in series_dict["lists"]["co2"]:
                variable = pfp_utils.convert_units_func(ds, variable, "gC/m^2")
                cdyr["variables"][item]["Attr"]["units"] = "gC/m^2"
            elif item in series_dict["lists"]["ET"]:
                variable = pfp_utils.convert_units_func(ds, variable, "kg/m^2")
                cdyr["variables"][item]["Attr"]["units"] = "kg/m^2"
            else:
                cdyr["variables"][item]["Attr"]["units"] = variable["Attr"]["units"]
            cdyr["variables"][item]["Data"] = numpy.ma.cumsum(variable["Data"])
            cdyr["variables"][item]["Attr"]["format"] = series_dict["cumulative"][item]["format"]
            cdyr["variables"][item]["Attr"]["units"] = cdyr["variables"][item]["Attr"]["units"]+"/year"
            # copy some of the variable attributes
            default_list = ["long_name", "height", "instrument"]
            descr_list = [d for d in list(variable["Attr"].keys()) if "description" in d]
            vattr_list = default_list + descr_list
            for attr in vattr_list:
                if attr in variable["Attr"]:
                    cdyr["variables"][item]["Attr"][attr] = variable["Attr"][attr]
    # cumulative total over all data
    cdyr = cumulative_dict["all"] = {"globalattributes":{}, "variables":{}}
    cdyr["globalattributes"] = copy.deepcopy(ds.globalattributes)
    cdyr["variables"]["DateTime"] = {"Data":dt["Data"], "Flag":dt["Flag"], "Attr":dt["Attr"]}
    cdyr["variables"]["DateTime"]["Attr"]["format"] = "dd/mm/yyyy HH:MM"
    for item in series_list:
        cdyr["variables"][item] = {"Data":[],"Attr":{}}
        variable = pfp_utils.GetVariable(ds, item)
        if item in series_dict["lists"]["co2"]:
            variable = pfp_utils.convert_units_func(ds, variable, "gC/m^2")
            cdyr["variables"][item]["Attr"]["units"] = "gC/m^2"
        elif item in series_dict["lists"]["ET"]:
            variable = pfp_utils.convert_units_func(ds, variable, "kg/m^2")
            cdyr["variables"][item]["Attr"]["units"] = "kg/m^2"
        else:
            cdyr["variables"][item]["Attr"]["units"] = variable["Attr"]["units"]
        cdyr["variables"][item]["Data"] = numpy.ma.cumsum(variable["Data"])
        cdyr["variables"][item]["Attr"]["format"] = series_dict["cumulative"][item]["format"]
        # copy some of the variable attributes
        default_list = ["long_name", "height", "instrument"]
        descr_list = [d for d in list(variable["Attr"].keys()) if "description" in d]
        vattr_list = default_list + descr_list
        for attr in vattr_list:
            if attr in variable["Attr"]:
                cdyr["variables"][item]["Attr"][attr] = variable["Attr"][attr]
    cdyr["globalattributes"]["nc_nrecs"] = len(cdyr["variables"]["DateTime"]["Data"])
    return cumulative_dict

def ParseL6ControlFile(cf, ds):
    """
    Purpose:
     Parse the L6 control file.
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
    """
    # create the L6 information dictionary
    l6_info = {}
    # summary section
    l6_info["Summary"] = {"EcosystemRespiration":[],
                          "NetEcosystemExchange": [],
                          "GrossPrimaryProductivity": []}
    # merge section
    l6_info["MergeSeries"] = {"standard": {}}
    # propagate the ['Files'] section
    l6_info["Files"] = copy.deepcopy(cf["Files"])
    # propagate the ['Options'] section
    l6_info["Options"] = copy.deepcopy(cf["Options"])
    # some useful global attributes
    l6_info["Global"] = {"site_name": ds.globalattributes["site_name"]}
    # add key for suppressing output of intermediate variables e.g. Ta_aws
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "KeepIntermediateSeries", default="No")
    l6_info["RemoveIntermediateSeries"] = {"KeepIntermediateSeries": opt, "not_output": []}
    if "EcosystemRespiration" in list(cf.keys()):
        l6_info["EcosystemRespiration"] = copy.deepcopy(cf["EcosystemRespiration"])
        for output in list(cf["EcosystemRespiration"].keys()):
            if "ERUsingSOLO" in list(cf["EcosystemRespiration"][output].keys()):
                rpSOLO_createdict(cf, ds, l6_info, output, "ERUsingSOLO", 610)
            if "ERUsingLloydTaylor" in list(cf["EcosystemRespiration"][output].keys()):
                rp_createdict(cf, ds, l6_info, output, "ERUsingLloydTaylor", 620)
            if "ERUsingLasslop" in list(cf["EcosystemRespiration"][output].keys()):
                rp_createdict(cf, ds, l6_info, output, "ERUsingLasslop", 630)
    if "NetEcosystemExchange" in list(cf.keys()):
        l6_info["NetEcosystemExchange"] = {}
        for output in list(cf["NetEcosystemExchange"].keys()):
            rpNEE_createdict(cf, ds, l6_info["NetEcosystemExchange"], output)
    if "GrossPrimaryProductivity" in list(cf.keys()):
        l6_info["GrossPrimaryProductivity"] = {}
        for output in list(cf["GrossPrimaryProductivity"].keys()):
            rpGPP_createdict(cf, ds, l6_info["GrossPrimaryProductivity"], output)
    return l6_info

def PartitionNEE(ds, l6_info):
    """
    Purpose:
     Partition NEE into GPP and ER.
     Input and output names are held in info['gpp'].
    Usage:
     pfp_rp.PartitionNEE(ds, info)
      where cf is a conbtrol file object
            ds is a data structure
    Side effects:
     Series to hold the GPP data are created in ds.
    Author: PRI
    Date: August 2014
    """
    if "GrossPrimaryProductivity" not in l6_info:
        return
    # make the L6 "description" attribute for the target variable
    descr_level = "description_" + ds.globalattributes["processing_level"]
    # calculate GPP from NEE and ER
    for label in list(l6_info["GrossPrimaryProductivity"].keys()):
        if ("NEE" not in l6_info["GrossPrimaryProductivity"][label] and
            "ER" not in l6_info["GrossPrimaryProductivity"][label]):
            continue
        NEE_label = l6_info["GrossPrimaryProductivity"][label]["NEE"]
        ER_label = l6_info["GrossPrimaryProductivity"][label]["ER"]
        output_label = l6_info["GrossPrimaryProductivity"][label]["output"]
        if NEE_label not in list(ds.series.keys()):
            continue
        NEE, NEE_flag, NEE_attr = pfp_utils.GetSeriesasMA(ds, NEE_label)
        if ER_label not in list(ds.series.keys()):
            continue
        ER, _, _ = pfp_utils.GetSeriesasMA(ds, ER_label)
        # calculate GPP
        # here we use the conventions from Chapin et al (2006)
        #  NEP = -1*NEE
        #  GPP = NEP + ER ==> GPP = -1*NEE + ER
        GPP = float(-1)*NEE + ER
        ds.series[output_label]["Data"] = GPP
        ds.series[output_label]["Flag"] = NEE_flag
        # copy the attributes
        attr = ds.series[output_label]["Attr"]
        attr["units"] = NEE_attr["units"]
        attr["long_name"] = "Gross Primary Productivity"
        attr[descr_level] = "Calculated as -1*" + NEE_label + " + " + ER_label
        ds.series[output_label]["Attr"] = attr
        l6_info["Summary"]["GrossPrimaryProductivity"].append(label)
    return

def cleanup_ustar_dict(ds, ustar_in):
    """
    Purpose:
     Clean up the ustar dictionary;
      - make sure all years are included
      - fill missing year values with the mean
    Usage:
    Author: PRI
    Date: September 2015
    """
    dt = pfp_utils.GetVariable(ds, "DateTime")
    ts = int(float(ds.globalattributes["time_step"]))
    cdt = dt["Data"] - datetime.timedelta(minutes=ts)
    data_years = sorted(list(set([ldt.year for ldt in cdt])))
    # get the years for which we have u* thresholds in ustar_in
    years = []
    for item in ustar_in:
        for year in ustar_in[item]:
            years.append(int(year))
    ustar_out = {}
    for year in data_years:
        ustar_out[str(year)] = {"ustar_mean": numpy.nan}
        for item in ["cf", "cpd", "mpt"]:
            if item in ustar_in:
                if str(year) in ustar_in[item]:
                    if ((not numpy.isnan(ustar_in[item][str(year)]["ustar_mean"])) and
                        (numpy.isnan(ustar_out[str(year)]["ustar_mean"]))):
                        ustar_out[str(year)]["ustar_mean"] = ustar_in[item][str(year)]["ustar_mean"]
    # get the average of good ustar threshold values
    good_values = []
    for year in sorted(list(ustar_out.keys())):
        if not numpy.isnan(ustar_out[year]["ustar_mean"]):
            good_values.append(ustar_out[year]["ustar_mean"])
    if len(good_values) == 0:
        msg = " No u* thresholds found, using default of 0.25 m/s"
        logger.error(msg)
        good_values = [0.25]
    ustar_threshold_mean = numpy.sum(numpy.array(good_values))/len(good_values)
    # replace missing vaues with mean
    for year in sorted(list(ustar_out.keys())):
        if numpy.isnan(ustar_out[year]["ustar_mean"]):
            ustar_out[year]["ustar_mean"] = ustar_threshold_mean
    return ustar_out

def check_for_missing_data(series_list, label_list):
    for item, label in zip(series_list, label_list):
        index = numpy.where(numpy.ma.getmaskarray(item) == True)[0]
        if len(index) != 0:
            msg = " GetERFromFc: missing data in series " + label
            logger.error(msg)
            return 0
    return 1

def get_ustar_thresholds(cf, ds):
    """
    Purpose
     Get the annual ustar thresholds from a results workbook or from the
     ustar_threshold section in the control file.
    """
    # try...except used in desparation ahead of the October 2021 workshop
    # let's see how long it stays here ...
    ustar_dict = {}
    ustar_out = {}
    try:
        if "cpd_filename" in cf["Files"]:
            results_name = os.path.join(cf["Files"]["file_path"], cf["Files"]["cpd_filename"])
            if os.path.isfile(results_name):
                ustar_dict["cpd"] = get_ustarthreshold_from_results(results_name)
            else:
                msg = " CPD results file not found (" + results_name + ")"
                logger.warning(msg)
        if "mpt_filename" in cf["Files"]:
            results_name = os.path.join(cf["Files"]["file_path"], cf["Files"]["mpt_filename"])
            if os.path.isfile(results_name):
                ustar_dict["mpt"] = get_ustarthreshold_from_results(results_name)
            else:
                msg = " MPT results file not found (" + results_name + ")"
                logger.warning(msg)
        if "ustar_threshold" in cf:
            ts = int(float(ds.globalattributes["time_step"]))
            ustar_dict["cf"] = get_ustarthreshold_from_cf(cf, ts)
        else:
            msg = " No source for ustar threshold found in " + os.path.basename(cf.filename)
        ustar_out = cleanup_ustar_dict(ds, ustar_dict)
    except Exception:
        msg = " An error occured getting the ustar threshold"
        logger.error(msg)
        ds.returncodes["value"] = 1
        ds.returncodes["message"] = msg
    return ustar_out

def get_daynight_indicator(ds, l6_info):
    Fsd, _, _ = pfp_utils.GetSeriesasMA(ds, "Fsd")
    # get the day/night indicator
    daynight_indicator = {"values":numpy.zeros(len(Fsd), dtype=numpy.int32), "attr":{}}
    inds = daynight_indicator["values"]
    attr = daynight_indicator["attr"]
    # get the filter type
    filter_type = pfp_utils.get_keyvaluefromcf(l6_info, ["Options"], "DayNightFilter",
                                               default="Fsd")
    attr["daynight_filter"] = filter_type
    use_fsdsyn = pfp_utils.get_keyvaluefromcf(l6_info, ["Options"], "UseFsdsyn_threshold",
                                              default="No")
    attr["use_fsdsyn"] = use_fsdsyn
    # get the indicator series
    if filter_type.lower() == "fsd":
        # get the Fsd threshold
        Fsd_threshold = int(pfp_utils.get_keyvaluefromcf(l6_info, ["Options"], "Fsd_threshold",
                                                         default=10))
        attr["Fsd_threshold"] = str(Fsd_threshold)
        # we are using Fsd only to define day/night
        idx = numpy.ma.where(Fsd <= Fsd_threshold)[0]
        inds[idx] = numpy.int32(1)
    elif filter_type.lower() == "sa":
        # get the solar altitude threshold
        sa_threshold = int(pfp_utils.get_keyvaluefromcf(l6_info, ["Options"], "sa_threshold",
                                                        default="-5"))
        attr["sa_threshold"] = str(sa_threshold)
        # we are using solar altitude to define day/night
        if "solar_altitude" not in list(ds.series.keys()):
            pfp_ts.get_synthetic_fsd(ds)
        sa, _, _ = pfp_utils.GetSeriesasMA(ds, "solar_altitude")
        idx = numpy.ma.where(sa < sa_threshold)[0]
        inds[idx] = numpy.int32(1)
    else:
        msg = "Unrecognised DayNightFilter option in L6 control file"
        raise Exception(msg)
    return daynight_indicator

def get_day_indicator(cf, ds):
    """
    Purpose:
     Returns a dictionary containing an indicator series and some attributes.
     The indicator series is 1 during day time and 0 at night time.  The threshold
     between night and day is the Fsd threshold specified in the control file.
    Usage:
     indicators["day"] = get_day_indicator(cf, ds)
     where;
      cf is a control file object
      ds is a data structure
    and;
      indicators["day"] is a dictionary containing
      indicators["day"]["Data"] is the indicator series
      indicators["day"]["Attr"] are the attributes
    Author: PRI
    Date: March 2016
    Mods:
     PRI 6/12/2018 - removed calculation of Fsd_syn by default
    """
    nrecs = int(ds.globalattributes["nc_nrecs"])
    Fsd = pfp_utils.GetVariable(ds, "Fsd")
    # indicator = 1 ==> day, indicator = 0 ==> night
    long_name = "Day time indicator, 1 ==> day, 0 ==> night"
    indicator_day = {"Label" : "indicator_day",
                     "Data": numpy.ones(nrecs, dtype=numpy.int32),
                     "Flag": numpy.zeros(nrecs, dtype=numpy.int32),
                     "Attr": {"long_name": long_name, "units": "none"}}
    inds = indicator_day["Data"]
    attr = indicator_day["Attr"]
    # get the filter type
    filter_type = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "DayNightFilter", default="Fsd")
    attr["daynight_filter_type"] = filter_type
    use_fsdsyn = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "UseFsdsyn_threshold", default="No")
    attr["use_fsdsyn"] = use_fsdsyn
    # get the indicator series
    if filter_type.lower() == "fsd":
        # get the Fsd threshold
        Fsd_threshold = int(pfp_utils.get_keyvaluefromcf(cf, ["Options"], "Fsd_threshold", default=10))
        attr["Fsd_threshold"] = str(Fsd_threshold)
        # we are using Fsd only to define day/night
        idx = numpy.ma.where(Fsd["Data"] <= Fsd_threshold)[0]
        inds[idx] = numpy.int32(0)
    elif filter_type.lower() == "sa":
        # get the solar altitude threshold
        sa_threshold = int(pfp_utils.get_keyvaluefromcf(cf, ["Options"], "sa_threshold", default="-5"))
        attr["sa_threshold"] = str(sa_threshold)
        # we are using solar altitude to define day/night
        if "solar_altitude" not in ds.series.keys():
            pfp_ts.get_synthetic_fsd(ds)
        sa = pfp_utils.GetVariable(ds, "solar_altitude")
        index = numpy.ma.where(sa["Data"] < sa_threshold)[0]
        inds[index] = numpy.int32(0)
    else:
        msg = "Unrecognised DayNightFilter option in control file"
        raise Exception(msg)
    return indicator_day

def get_evening_indicator(cf, ds):
    """
    Purpose:
     Returns a dictionary containing an indicator series and some attributes.
     The indicator series is 1 during the evening and 0 at all other times.
     Evening is defined as the period between sunset and the number of hours
     specified in the control file [Options] section as the EveningFilterLength
     key.
    Usage:
     indicators["evening"] = get_evening_indicator(cf, ds)
     where;
      cf is a control file object
      ds is a data structure
    and;
      indicators["evening"] is a dictionary containing
      indicators["evening"]["Data"] is the indicator series
      indicators["evening"]["Attr"] are the attributes
    Author: PRI
    Date: March 2016
    """
    nrecs = int(ds.globalattributes["nc_nrecs"])
    ts = int(float(ds.globalattributes["time_step"]))
    # indicator series, 1 ==> evening
    long_name = "Evening indicator, 1 ==> evening hours (after sunset)"
    indicator_evening = {"Label": "indicator_evening",
                         "Data": numpy.zeros(nrecs, dtype=numpy.int32),
                         "Flag": numpy.zeros(nrecs, dtype=numpy.int32),
                         "Attr": {"long_name": long_name, "units": "none"}}
    attr = indicator_evening["Attr"]
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "EveningFilterLength", default="3")
    num_hours = int(opt)
    if num_hours <= 0 or num_hours >= 12:
        indicator_evening["Data"] = numpy.zeros(nrecs)
        indicator_evening["Attr"]["evening_filter_length"] = str(num_hours)
        msg = " Evening filter period outside 0 to 12 hours, skipping ..."
        logger.warning(msg)
        return indicator_evening
    night_indicator = get_night_indicator(cf, ds)
    day_indicator = get_day_indicator(cf, ds)
    ntsperhour = int(0.5 + float(60)/float(ts))
    shift = num_hours*ntsperhour
    day_indicator_shifted = numpy.roll(day_indicator["Data"], shift)
    indicator_evening["Data"] = night_indicator["Data"]*day_indicator_shifted
    attr["evening_filter_length"] = str(num_hours)
    return indicator_evening

def get_night_indicator(cf, ds):
    """
    Purpose:
     Returns a dictionary containing an indicator series and some attributes.
     The indicator series is 1 during night time and 0 during the day.  The
     threshold for determining night and day is the Fsd threshold
     given in the control file [Options] section.
    Usage:
     indicators["night"] = get_night_indicator(cf, ds)
     where;
      cf is a control file object
      ds is a data structure
    and;
      indicators["night"] is a dictionary containing
      indicators["night"]["Data"] is the indicator series
      indicators["night"]["Attr"] are the attributes
    Author: PRI
    Date: March 2016
    """
    nrecs = int(ds.globalattributes["nc_nrecs"])
    Fsd = pfp_utils.GetVariable(ds, "Fsd")
    # indicator = 1 ==> night, indicator = 0 ==> day
    long_name = "Night time indicator, 1 ==> night, 0 ==> day"
    indicator_night = {"Label" : "indicator_night",
                       "Data": numpy.ones(nrecs, dtype=numpy.int32),
                       "Flag": numpy.zeros(nrecs, dtype=numpy.int32),
                       "Attr": {"long_name": long_name, "units": "none"}}
    inds = indicator_night["Data"]
    attr = indicator_night["Attr"]
    # get the filter type
    filter_type = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "DayNightFilter", default="Fsd")
    attr["daynight_filter_type"] = filter_type
    use_fsdsyn = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "UseFsdsyn_threshold", default="No")
    attr["use_fsdsyn"] = use_fsdsyn
    # get the indicator series
    if filter_type.lower() == "fsd":
        # get the Fsd threshold
        Fsd_threshold = int(pfp_utils.get_keyvaluefromcf(cf, ["Options"], "Fsd_threshold", default=10))
        attr["Fsd_threshold"] = str(Fsd_threshold)
        # we are using Fsd only to define day/night
        idx = numpy.ma.where(Fsd["Data"] <= Fsd_threshold)[0]
        inds[idx] = numpy.int32(1)
    elif filter_type.lower() == "sa":
        # get the solar altitude threshold
        sa_threshold = int(pfp_utils.get_keyvaluefromcf(cf, ["Options"], "sa_threshold", default="-5"))
        attr["sa_threshold"] = str(sa_threshold)
        # we are using solar altitude to define day/night
        if "solar_altitude" not in ds.series.keys():
            pfp_ts.get_synthetic_fsd(ds)
        sa = pfp_utils.GetVariable(ds, "solar_altitude")
        index = numpy.ma.where(sa["Data"] < sa_threshold)[0]
        inds[index] = numpy.int32(1)
    else:
        msg = "Unrecognised DayNightFilter option in control file"
        raise Exception(msg)
    return indicator_night

def get_turbulence_indicator_ustar_basic(ldt, ustar, ustar_dict):
    """
    Purpose:
     Returns a dictionary containing an indicator series and some attributes.
     The indicator series is 1 when ustar is above the threshold and 0 when
     ustar is below the threshold.
     By default, all day time observations are accepted regardless of ustar value.
    Usage:
     indicators["turbulence"] = get_turbulence_indicator_ustar_basic(ldt,ustar,ustar_dict)
     where;
      ldt is a list of datetimes
      ustar is a series of ustar values (ndarray)
      ustar_dict is a dictionary of ustar thresholds returned by pfp_rp.get_ustar_thresholds
      ts is the time step for ustar
    and;
     indicators["turbulence"] is a dictionary containing
      indicators["turbulence"]["Data"] is the indicator series
      indicators["turbulence"]["Attr"] are the attributes
    Author: PRI
    Date: March 2016
    """
    nrecs = len(ldt["Data"])
    ts = int(ustar["time_step"])
    years = sorted(list(ustar_dict.keys()))
    # now loop over the years in the data to apply the ustar threshold
    long_name = "Indicator for basic ustar filter, 1 ==> turbulent"
    indicator_turbulence = {"basic": {"Label": "indicator_turbulence_basic",
                                      "Data": numpy.zeros(nrecs),
                                      "Flag": numpy.zeros(nrecs),
                                      "Attr": {"long_name": long_name,
                                               "units": "none"}}}
    ustar_basic = indicator_turbulence["basic"]["Data"]
    attr = indicator_turbulence["basic"]["Attr"]
    attr["turbulence_filter"] = "ustar_basic"
    for year in years:
        start_date = datetime.datetime(int(year), 1, 1, 0, 0) + datetime.timedelta(minutes=ts)
        end_date = datetime.datetime(int(year)+1, 1, 1, 0, 0)
        # get the ustar threshold
        ustar_threshold = float(ustar_dict[year]["ustar_mean"])
        attr["ustar_threshold_" + str(year)] = str(ustar_threshold)
        # get the start and end datetime indices
        si = pfp_utils.GetDateIndex(ldt["Data"], start_date, ts=ts, default=0, match="exact")
        ei = pfp_utils.GetDateIndex(ldt["Data"], end_date, ts=ts, default=nrecs-1, match="exact")
        # set the QC flag
        idx = numpy.ma.where(ustar["Data"][si:ei] >= ustar_threshold)[0]
        ustar_basic[si:ei][idx] = numpy.int32(1)
    indicator_turbulence["basic"]["Data"] = ustar_basic
    return indicator_turbulence

def get_turbulence_indicator_ustar_evgb(ldt, ustar, ustar_dict, indicator_day):
    """
    Purpose:
     Returns a dictionary containing an indicator series and some attributes.
     The indicator series is 1 when ustar is above the threshold after sunset
     and remains 1 until ustar falls below the threshold after which it remains
     0 until the following evening.
     By default, all day time observations are accepted regardless of ustar value.
     Based on a ustar filter scheme designed by Eva van Gorsel for use at the
     Tumbarumba site.
    Usage:
     indicators["turbulence"] = get_turbulence_indicator_ustar_evgb(ldt, ustar, ustar_dict, ind_day)
     where;
      ldt is a list of datetimes
      ind_day is a day/night indicator
      ustar is a series of ustar values (ndarray)
      ustar_dict is a dictionary of ustar thresholds returned by pfp_rp.get_ustar_thresholds
      ind_day is a day/night indicator
    and;
     indicators["turbulence"] is a dictionary containing
      indicators["turbulence"]["Data"] is the indicator series
      indicators["turbulence"]["Attr"] are the attributes
    Author: PRI, EVG, WW
    Date: December 2016
    """
    nrecs = len(ldt["Data"])
    years = sorted(list(ustar_dict.keys()))
    # initialise the return dictionary
    long_name_basic = "Indicator for basic ustar filter, 1 ==> turbulent"
    long_name_evgb = "Indicator for EvGB ustar filter, 1 ==> turbulent"
    indicator_turbulence = {"basic": {"Label": "indicator_turbulence_basic",
                                      "Data": numpy.zeros(nrecs),
                                      "Flag": numpy.zeros(nrecs),
                                      "Attr": {"long_name": long_name_basic,
                                               "units": "none"}},
                            "evgb": {"Label": "indicator_turbulence_evgb",
                                      "Data": numpy.zeros(nrecs),
                                      "Flag": numpy.zeros(nrecs),
                                      "Attr": {"long_name": long_name_evgb,
                                               "units": "none"}}}
    attr = indicator_turbulence["evgb"]["Attr"]
    attr["turbulence_filter"] = "ustar_evgb"
    # get the basic ustar filter indicator series
    # ustar >= threshold ==> ind_ustar = 1, ustar < threshold == ind_ustar = 0
    ustar_basic = get_turbulence_indicator_ustar_basic(ldt, ustar, ustar_dict)
    indicator_turbulence["basic"] = copy.deepcopy(ustar_basic["basic"])
    # there may be a better way to do this than looping over all elements
    # keep_going is a logical that is True as long as ustar is above the threshold
    # after sunset and is False once ustar drops below the threshold
    # keep_going controls rejection of the rest of the nocturnal data once ustar
    # falls below the threshold
    keep_going = False
    ustar_evgb = numpy.zeros(nrecs, dtype=int)
    # loop over all records
    for i in range(nrecs):
        if indicator_day[i] == 1:
            # day time ==> reset logical, turbulence indicator = basic
            keep_going = True
            ustar_evgb[i] = indicator_turbulence["basic"]["Data"][i]
        else:
            # night time
            if indicator_turbulence["basic"]["Data"][i] == 1 and keep_going:
                # ustar still above threshold, turbulence indicator = basic
                ustar_evgb[i] = indicator_turbulence["basic"]["Data"][i]
            else:
                # ustar dropped below threshold, turbulence indicator = 0
                ustar_evgb[i] = 0
                # reject the rest of this night
                keep_going = False
    # put the ustar thrtesholds into the variable attributes
    for year in years:
        attr["ustar_threshold_" + str(year)] = str(ustar_dict[year]["ustar_mean"])
    # apply the EvGB filter to the basic ustar filter
    indicator_turbulence["evgb"]["Data"] = ustar_basic["basic"]["Data"]*ustar_evgb
    return indicator_turbulence

def get_turbulence_indicator_ustar_fluxnet(ldt, ustar, ustar_dict):
    """
    Purpose:
     Returns a dictionary containing an indicator series and some attributes.
     The indicator series is:
      - 1 when ustar is above the threshold
      - 0 when ustar is below the threshold
      - 0 when ustar is above the threshold for the first time following a period
          when ustar has been below the threshold.
     This is the FluxNet ustar filter from Pastorello et al 2020 (https://doi.org/10.1038/s41597-020-0534-3).
    Usage:
     indicators["turbulence"] = get_turbulence_indicator_ustar_fluxnet(ldt,ustar,ustar_dict)
     where;
      ldt is a datetime val
      ustar is a ustar variable
      ustar_dict is a dictionary of ustar thresholds returned by pfp_rp.get_ustar_thresholds
    and;
     indicators["turbulence"] is a dictionary containing
      indicators["turbulence"]["values"] is the indicator series
      indicators["turbulence"]["attr"] are the attributes
    Author: PRI
    Date: October 2020
    """
    nrecs = len(ldt["Data"])
    ts = int(ustar["time_step"])
    years = sorted(list(ustar_dict.keys()))
    # initialise the return dictionary
    long_name_basic = "Indicator for basic ustar filter, 1 ==> turbulent"
    long_name_fluxnet = "Indicator for FluxNet ustar filter, 1 ==> turbulent"
    indicator_turbulence = {"basic": {"Label": "indicator_turbulence_basic",
                                      "Data": numpy.zeros(nrecs, dtype=int),
                                      "Flag": numpy.zeros(nrecs, dtype=int),
                                      "Attr": {"long_name": long_name_basic,
                                               "units": "none"}},
                            "fluxnet": {"Label": "indicator_turbulence_fluxnet",
                                        "Data": numpy.zeros(nrecs, dtype=int),
                                        "Flag": numpy.zeros(nrecs, dtype=int),
                                        "Attr": {"long_name": long_name_fluxnet,
                                                 "units": "none"}}}
    ustar_basic = indicator_turbulence["basic"]["Data"]
    ustar_fluxnet = indicator_turbulence["fluxnet"]["Data"]
    attr = indicator_turbulence["fluxnet"]["Attr"]
    attr["turbulence_filter"] = "ustar_fluxnet"
    # get the list of years
    for year in years:
        start_date = datetime.datetime(int(year), 1, 1, 0, 0) + datetime.timedelta(minutes=ts)
        end_date = datetime.datetime(int(year)+1, 1, 1, 0, 0)
        # get the ustar threshold
        ustar_threshold = float(ustar_dict[year]["ustar_mean"])
        attr["ustar_threshold_" + str(year)] = str(ustar_threshold)
        # get the start and end datetime indices
        si = pfp_utils.GetDateIndex(ldt["Data"], start_date, ts=ts, default=0, match="exact")
        ei = pfp_utils.GetDateIndex(ldt["Data"], end_date, ts=ts, default=nrecs-1, match="exact")
        # basic ustar filter
        # ustar >= threshold ==> ustar_basic = 1
        idx = numpy.ma.where(ustar["Data"][si:ei] >= ustar_threshold)[0]
        ustar_basic[si:ei][idx] = int(1)
        # FluxNet ustar filter
        # first period with ustar >= threshold ==> ustar_fluxnet = 0
        ustar_fluxnet[si:ei] = ustar_basic[si:ei] * numpy.roll(ustar_basic[si:ei], 1)
        if ustar_basic[si] < ustar_threshold:
            ustar_fluxnet[si:si+2] = int(0)
    indicator_turbulence["basic"]["Data"] = ustar_basic
    indicator_turbulence["fluxnet"]["Data"] = ustar_fluxnet
    return indicator_turbulence

def get_ustarthreshold_from_cf(cf, ts):
    """
    Purpose:
     Returns a dictionary containing ustar thresholds for each year read from
     the control file.  If no [ustar_threshold] section is found then a
     default value of 0.25 is used.
    Usage:
     ustar_dict = pfp_rp.get_ustarthreshold_from_cf(cf)
     where cf is the control file object
    Author: PRI
    Date: July 2015
    """
    td = dateutil.relativedelta.relativedelta(years=1)
    ustar_dict = collections.OrderedDict()
    ustar_threshold_list = []
    msg = " Using values from control file ustar_threshold section"
    logger.info(msg)
    for n in list(cf["ustar_threshold"].keys()):
        ustar_string = cf["ustar_threshold"][str(n)]
        ustar_list = ustar_string.split(",")
        ustar_threshold_list.append(ustar_list)
    for item in ustar_threshold_list:
        start_date = dateutil.parser.parse(item[0]) - datetime.timedelta(minutes=ts)
        end_date = dateutil.parser.parse(item[1]) - datetime.timedelta(minutes=ts)
        years = [dt.year for dt in pfp_utils.perdelta(start_date, end_date, td)]
        for year in years:
            ustar_dict[str(year)] = {}
            ustar_dict[str(year)]["ustar_mean"] = float(item[2])
    return ustar_dict

def get_ustarthreshold_from_results(results_name):
    """
    Purpose:
     Returns a dictionary containing ustar thresholds for each year read from
     the CPD or MPT results file.  If there is no results file name found in the
     control file then return an empty dictionary.
    Usage:
     ustar_dict = pfp_rp.get_ustarthreshold_from_results(results_name)
     where results_name is the CPD or MPT results file name
           ustar_dict is a dictionary of ustar thresholds, 1 entry per year
    Author: PRI
    Date: July 2015
          October 2021 - rewrite to use pandas, add trap for failed open
    """
    df = pandas.read_excel(results_name, sheet_name="Annual", index_col=0)
    df.index = df.index.map(str)
    ustar_dict = df.to_dict('index')
    return ustar_dict

def get_ustar_thresholds_annual(ldt,ustar_threshold):
    """
    Purpose:
     Returns a dictionary containing ustar thresholds for all years using
     a single value enetred as the ustar_threshold argument.
    Usage:
     ustar_dict = pfp_rp.get_ustar_thresholds_annual(ldt,ustar_threshold)
     where ldt is a list of datetime objects
           ustar_threshold is the value to be used
    Author: PRI
    Date: July 2015
    """
    ustar_dict = collections.OrderedDict()
    if not isinstance(ustar_threshold,float):
        ustar_threshold = float(ustar_threshold)
    start_year = ldt[0].year
    end_year = ldt[-1].year
    for year in range(start_year,end_year+1):
        ustar_dict[year] = {}
        ustar_dict[year]["ustar_mean"] = ustar_threshold
    return ustar_dict

def rpGPP_createdict(cf, ds, info, label):
    """ Creates a dictionary in ds to hold information about calculating GPP."""
    # create the dictionary keys for this series
    info[label] = {}
    # output series name
    info[label]["output"] = label
    # net ecosystem exchange
    default = label.replace("GPP", "NEE")
    opt = pfp_utils.get_keyvaluefromcf(cf, ["GrossPrimaryProductivity", label], "NEE", default=default)
    info[label]["NEE"] = opt
    # ecosystem respiration
    default = label.replace("GPP", "ER")
    opt = pfp_utils.get_keyvaluefromcf(cf, ["GrossPrimaryProductivity", label], "ER", default=default)
    info[label]["ER"] = opt
    # create an empty series in ds if the output series doesn't exist yet
    if info[label]["output"] not in list(ds.series.keys()):
        data, flag, attr = pfp_utils.MakeEmptySeries(ds, info[label]["output"])
        pfp_utils.CreateSeries(ds, info[label]["output"], data, flag, attr)
    return

def rpMergeSeries_createdict(cf, ds, l6_info, label, called_by):
    """ Creates a dictionary in ds to hold information about the merging of gap filled
        and tower data."""
    nrecs = int(ds.globalattributes["nc_nrecs"])
    # create the merge directory in the info dictionary
    if called_by not in l6_info:
        l6_info[called_by] = {}
    if "standard" not in list(l6_info[called_by].keys()):
        l6_info[called_by]["standard"] = {}
    # create the dictionary keys for this series
    l6_info[called_by]["standard"][label] = {}
    # output series name
    l6_info[called_by]["standard"][label]["output"] = label
    # source
    sources = pfp_utils.GetMergeSeriesKeys(cf, label, section="EcosystemRespiration")
    l6_info[called_by]["standard"][label]["source"] = sources
    # create an empty series in ds if the output series doesn't exist yet
    if l6_info[called_by]["standard"][label]["output"] not in list(ds.series.keys()):
        variable = pfp_utils.CreateEmptyVariable(label, nrecs)
        pfp_utils.CreateVariable(ds, variable)
    return

def rpNEE_createdict(cf, ds, info, label):
    """ Creates a dictionary in ds to hold information about calculating NEE."""
    # create the dictionary keys for this series
    info[label] = {}
    # output series name
    info[label]["output"] = label
    # CO2 flux
    sl = ["NetEcosystemExchange", label]
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "Fco2", default="Fco2")
    info[label]["Fco2"] = opt
    # ecosystem respiration
    default = label.replace("NEE", "ER")
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "ER", default=default)
    info[label]["ER"] = opt
    # create an empty series in ds if the output series doesn't exist yet
    if info[label]["output"] not in list(ds.series.keys()):
        data, flag, attr = pfp_utils.MakeEmptySeries(ds, info[label]["output"])
        pfp_utils.CreateSeries(ds, info[label]["output"], data, flag, attr)
    return

def rpSOLO_createdict(cf, ds, l6_info, output, called_by, flag_code):
    """
    Purpose:
     Creates a dictionary in l6_info to hold information about the SOLO data
     used to estimate ecosystem respiration.
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
    """
    nrecs = int(ds.globalattributes["nc_nrecs"])
    # make the L6 "description" attrubute for the target variable
    descr_level = "description_" + ds.globalattributes["processing_level"]
    # create the dictionary keys for this series
    if called_by not in list(l6_info.keys()):
        l6_info[called_by] = {"outputs": {}, "info": {"source": "Fco2", "target": "ER"}, "gui": {}}
        # only need to create the ["info"] dictionary on the first pass
        pfp_gf.gfSOLO_createdict_info(cf, ds, l6_info, called_by)
        if ds.returncodes["value"] != 0:
            return
        # only need to create the ["gui"] dictionary on the first pass
        pfp_gf.gfSOLO_createdict_gui(cf, ds, l6_info, called_by)
    # get the outputs section
    pfp_gf.gfSOLO_createdict_outputs(cf, l6_info, output, called_by, flag_code)
    # create an empty series in ds if the SOLO output series doesn't exist yet
    Fco2 = pfp_utils.GetVariable(ds, l6_info[called_by]["info"]["source"])
    model_outputs = list(cf["EcosystemRespiration"][output][called_by].keys())
    for model_output in model_outputs:
        if model_output not in list(ds.series.keys()):
            # create an empty variable
            variable = pfp_utils.CreateEmptyVariable(model_output, nrecs)
            variable["Attr"]["long_name"] = "Ecosystem respiration"
            variable["Attr"]["drivers"] = l6_info[called_by]["outputs"][model_output]["drivers"]
            variable["Attr"][descr_level] = "Modeled by neural network (SOLO)"
            variable["Attr"]["target"] = l6_info[called_by]["info"]["target"]
            variable["Attr"]["source"] = l6_info[called_by]["info"]["source"]
            variable["Attr"]["units"] = Fco2["Attr"]["units"]
            pfp_utils.CreateVariable(ds, variable)
    return

def rp_createdict(cf, ds, l6_info, output, called_by, flag_code):
    """
    Purpose:
     Creates a dictionary in ds to hold information about estimating ecosystem
     respiration
    Usage:
    Side effects:
    Author: PRI, IM updated to prevent code duplication of LT and LL methods
    Date August 2019
    """

    # Create a dict to set the description_l6 attribute
    description_dict = {'ERUsingLasslop': "Modeled by Lasslop et al. (2010)",
                        'ERUsingLloydTaylor': "Modeled by Lloyd-Taylor (1994)"}
    nrecs = int(ds.globalattributes["nc_nrecs"])
    # create the settings directory
    if called_by not in l6_info.keys():
        l6_info[called_by] = {"outputs": {}, "info": {}, "gui": {}}
    # get the info section
    rp_createdict_info(cf, ds, l6_info[called_by], called_by)
    if ds.returncodes["value"] != 0:
        return
    # get the outputs section
    rp_createdict_outputs(cf, l6_info[called_by], output, called_by, flag_code)
    # create an empty series in ds if the output series doesn't exist yet
    Fc = pfp_utils.GetVariable(ds, l6_info[called_by]["info"]["source"])
    model_outputs = cf["EcosystemRespiration"][output][called_by].keys()
    for model_output in model_outputs:
        if model_output not in ds.series.keys():
            # create an empty variable
            variable = pfp_utils.CreateEmptyVariable(model_output, nrecs)
            variable["Attr"]["long_name"] = "Ecosystem respiration"
            variable["Attr"]["drivers"] = l6_info[called_by]["outputs"][model_output]["drivers"]
            variable["Attr"]["description_l6"] = description_dict[called_by]
            variable["Attr"]["target"] = l6_info[called_by]["info"]["target"]
            variable["Attr"]["source"] = l6_info[called_by]["info"]["source"]
            variable["Attr"]["units"] = Fc["Attr"]["units"]
            pfp_utils.CreateVariable(ds, variable)
    return

def rp_createdict_info(cf, ds, erl, called_by):
    """
    Purpose:
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
          June 2019 - modified for new l5_info structure
    """
    # Create a dict to set the file_suffix and extension
    suffix_dict = {'ERUsingLasslop': "_Lasslop.xlsx",
                   'ERUsingLloydTaylor': "_LloydTaylor.xlsx"}
    # reset the return message and code
    ds.returncodes["message"] = "OK"
    ds.returncodes["value"] = 0
    # time step
    time_step = int(ds.globalattributes["time_step"])
    # get the level of processing
    level = ds.globalattributes["processing_level"]
    # local pointer to the datetime series
    ldt = ds.series["DateTime"]["Data"]
    # add an info section to the info["solo"] dictionary
    erl["info"]["file_startdate"] = ldt[0].strftime("%Y-%m-%d %H:%M")
    erl["info"]["file_enddate"] = ldt[-1].strftime("%Y-%m-%d %H:%M")
    erl["info"]["startdate"] = ldt[0].strftime("%Y-%m-%d %H:%M")
    erl["info"]["enddate"] = ldt[-1].strftime("%Y-%m-%d %H:%M")
    erl["info"]["called_by"] = called_by
    erl["info"]["time_step"] = time_step
    erl["info"]["source"] = "Fco2"
    erl["info"]["target"] = "ER"
    # check to see if this is a batch or an interactive run
    call_mode = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "call_mode", default="interactive")
    erl["info"]["call_mode"] = call_mode
    erl["gui"]["show_plots"] = False
    if call_mode.lower() == "interactive":
        erl["gui"]["show_plots"] = True
    # truncate to last date in Imports?
    truncate = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "TruncateToImports", default="Yes")
    erl["info"]["truncate_to_imports"] = truncate
    # number of records per day and maximum lags
    nperhr = int(float(60)/time_step + 0.5)
    erl["info"]["nperday"] = int(float(24)*nperhr + 0.5)
    erl["info"]["maxlags"] = int(float(12)*nperhr + 0.5)
    # Get the data path
    path_name = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "file_path")
    file_name = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "out_filename")
    file_name = file_name.replace(".nc", suffix_dict[called_by])
    erl['info']['data_file_path'] = os.path.join(path_name, file_name)
    # get the plot path
    plot_path = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="./plots/")
    plot_path = os.path.join(plot_path, level, "")
    if not os.path.exists(plot_path):
        try:
            os.makedirs(plot_path)
        except OSError:
            msg = "Unable to create the plot path " + plot_path + "\n"
            msg = msg + "Press 'Quit' to edit the control file.\n"
            msg = msg + "Press 'Continue' to use the default path.\n"
            result = pfp_gui.MsgBox_ContinueOrQuit(msg, title="Warning: L6 plot path")
            if result.clickedButton().text() == "Quit":
                # user wants to edit the control file
                msg = " Quitting L6 to edit control file"
                logger.warning(msg)
                ds.returncodes["message"] = msg
                ds.returncodes["value"] = 1
            else:
                plot_path = "./plots/"
                cf["Files"]["plot_path"] = "./plots/"
    erl["info"]["plot_path"] = plot_path
    return

def rp_createdict_outputs(cf, erl, target, called_by, flag_code):
    """Where's the docstring ya bastard?!"""
    var_dict = {'ERUsingLasslop': "LL",
                'ERUsingLloydTaylor': "LT"}
    eo = erl["outputs"]
    # loop over the outputs listed in the control file
    section = "EcosystemRespiration"
    outputs = cf[section][target][called_by].keys()
    for output in outputs:
        # create the dictionary keys for this series
        eo[output] = {}
        # get the target
        sl = [section, target, called_by, output]
        eo[output]["target"] = pfp_utils.get_keyvaluefromcf(cf, sl, "target", default=target)
        eo[output]["source"] = pfp_utils.get_keyvaluefromcf(cf, sl, "source", default=target)
        # add the flag_code
        eo[output]["flag_code"] = flag_code
        # list of drivers
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "drivers", default="Ta")
        eo[output]["drivers"] = pfp_utils.string_to_list(opt)
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "weights_air_soil", default="1")
        eo[output]["weights_air_soil"] = pfp_utils.string_to_list(opt)
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "output_plots", default="False")
        eo[output]["output_plots"] = (opt == "True")
        # fit statistics for plotting later on
        eo[output]["results"] = {"startdate":[],"enddate":[],"No. points":[],"r":[],
                                 "Bias":[],"RMSE":[],"Frac Bias":[],"NMSE":[],
                                 "Avg (obs)":[],"Avg (" + var_dict[called_by] + ")":[],
                                 "Var (obs)":[],"Var (" + var_dict[called_by] + ")":[],"Var ratio":[],
                                 "m_ols":[],"b_ols":[]}
    return

def rp_initplot(**kwargs):
    # set the margins, heights, widths etc
    pd = {"margin_bottom":0.075,"margin_top":0.075,"margin_left":0.05,"margin_right":0.05,
          "xy_height":0.20,"xy_width":0.20,"xyts_space":0.05,"xyts_space":0.05,
          "ts_width":0.9}
    # set the keyword arguments
    for key, value in kwargs.items():
        pd[key] = value
    # calculate bottom of the first time series and the height of the time series plots
    pd["ts_bottom"] = pd["margin_bottom"]+pd["xy_height"]+pd["xyts_space"]
    pd["ts_height"] = (1.0 - pd["margin_top"] - pd["ts_bottom"])/float(pd["nDrivers"]+1)
    return pd

def rp_plot(pd, ds, output, drivers, target, iel, called_by, si=0, ei=-1):
    """ Plot the results of the respiration run """
    mode_dict = {'ERUsingLasslop': 'LL', 'ERUsingLloydTaylor': 'LT'}
    mode = mode_dict[called_by]

    if called_by == 'ERUsingLasslop': mode = 'LL'
    if called_by == 'ERUsingLloydTaylor': mode = 'LT'

    ieli = iel["info"]
    ielo = iel["outputs"]
    # get a local copy of the datetime series
    if ei == -1:
        dt = ds.series['DateTime']['Data'][si:]
    else:
        dt = ds.series['DateTime']['Data'][si:ei+1]
    xdt = numpy.array(dt)
    # get the observed and modelled values
    obs, f, a = pfp_utils.GetSeriesasMA(ds, target, si=si, ei=ei)
    mod, f, a = pfp_utils.GetSeriesasMA(ds, output, si=si, ei=ei)
    # make the figure
    if iel["gui"]["show_plots"]:
        plt.ion()
    else:
        plt.ioff()
    fig = plt.figure(pd["fig_num"], figsize=(13, 8))
    fig.clf()
    fig.canvas.set_window_title(target + " (" + mode + "): " + pd["startdate"]
                                + " to " + pd["enddate"])
    plt.figtext(0.5, 0.95, pd["title"], ha='center', size=16)
    # XY plot of the diurnal variation
    rect1 = [0.10, pd["margin_bottom"], pd["xy_width"], pd["xy_height"]]
    ax1 = plt.axes(rect1)
    # get the diurnal stats of the observations
    mask = numpy.ma.mask_or(obs.mask, mod.mask)
    obs_mor = numpy.ma.array(obs, mask=mask)
    dstats = pfp_utils.get_diurnalstats(dt, obs_mor, ieli)
    ax1.plot(dstats["Hr"], dstats["Av"], 'b-', label="Obs")
    # get the diurnal stats of all predictions
    dstats = pfp_utils.get_diurnalstats(dt, mod, ieli)
    ax1.plot(dstats["Hr"], dstats["Av"], 'r-', label=mode + "(all)")
    mod_mor = numpy.ma.masked_where(numpy.ma.getmaskarray(obs) == True, mod, copy=True)
    dstats = pfp_utils.get_diurnalstats(dt, mod_mor, ieli)
    ax1.plot(dstats["Hr"], dstats["Av"], 'g-', label=mode + "(obs)")
    plt.xlim(0, 24)
    plt.xticks([0, 6, 12, 18, 24])
    ax1.set_ylabel(target)
    ax1.set_xlabel('Hour')
    ax1.legend(loc='upper right', frameon=False, prop={'size':8})
    # XY plot of the 30 minute data
    rect2 = [0.40, pd["margin_bottom"], pd["xy_width"], pd["xy_height"]]
    ax2 = plt.axes(rect2)
    ax2.plot(mod, obs, 'b.')
    ax2.set_ylabel(target + '_obs')
    ax2.set_xlabel(target + '_' + mode)
    # plot the best fit line
    coefs = numpy.ma.polyfit(numpy.ma.copy(mod), numpy.ma.copy(obs), 1)
    xfit = numpy.ma.array([numpy.ma.minimum.reduce(mod), numpy.ma.maximum.reduce(mod)])
    yfit = numpy.polyval(coefs, xfit)
    r = numpy.ma.corrcoef(mod, obs)
    ax2.plot(xfit, yfit, 'r--', linewidth=3)
    eqnstr = 'y = %.3fx + %.3f, r = %.3f'%(coefs[0], coefs[1], r[0][1])
    ax2.text(0.5, 0.875, eqnstr, fontsize=8, horizontalalignment='center', transform=ax2.transAxes)
    # write the fit statistics to the plot
    numpoints = numpy.ma.count(obs)
    numfilled = numpy.ma.count(mod)-numpy.ma.count(obs)
    diff = mod - obs
    bias = numpy.ma.average(diff)
    ielo[output]["results"]["Bias"].append(bias)
    rmse = numpy.ma.sqrt(numpy.ma.mean((obs-mod)*(obs-mod)))
    plt.figtext(0.725, 0.225, 'No. points')
    plt.figtext(0.825, 0.225, str(numpoints))
    ielo[output]["results"]["No. points"].append(numpoints)
    plt.figtext(0.725, 0.200, 'No. filled')
    plt.figtext(0.825, 0.200, str(numfilled))
    plt.figtext(0.725, 0.175, 'Slope')
    plt.figtext(0.825, 0.175, str(pfp_utils.round2significant(coefs[0], 4)))
    ielo[output]["results"]["m_ols"].append(coefs[0])
    plt.figtext(0.725, 0.150, 'Offset')
    plt.figtext(0.825, 0.150, str(pfp_utils.round2significant(coefs[1], 4)))
    ielo[output]["results"]["b_ols"].append(coefs[1])
    plt.figtext(0.725, 0.125, 'r')
    plt.figtext(0.825, 0.125, str(pfp_utils.round2significant(r[0][1], 4)))
    ielo[output]["results"]["r"].append(r[0][1])
    plt.figtext(0.725, 0.100, 'RMSE')
    plt.figtext(0.825, 0.100, str(pfp_utils.round2significant(rmse, 4)))
    ielo[output]["results"]["RMSE"].append(rmse)
    var_obs = numpy.ma.var(obs)
    ielo[output]["results"]["Var (obs)"].append(var_obs)
    var_mod = numpy.ma.var(mod)
    ielo[output]["results"]["Var (" + mode + ")"].append(var_mod)
    ielo[output]["results"]["Var ratio"].append(var_obs/var_mod)
    ielo[output]["results"]["Avg (obs)"].append(numpy.ma.average(obs))
    ielo[output]["results"]["Avg (" + mode + ")"].append(numpy.ma.average(mod))
    # time series of drivers and target
    ts_axes = []
    rect = [pd["margin_left"], pd["ts_bottom"], pd["ts_width"], pd["ts_height"]]
    ts_axes.append(plt.axes(rect))
    ts_axes[0].plot(xdt, obs, 'b.')
    ts_axes[0].scatter(xdt, obs)
    ts_axes[0].plot(xdt, mod, 'r-')
    plt.axhline(0)
    ts_axes[0].set_xlim(xdt[0], xdt[-1])
    TextStr = target + '_obs (' + ds.series[target]['Attr']['units'] + ')'
    ts_axes[0].text(0.05, 0.85, TextStr, color='b', horizontalalignment='left', transform=ts_axes[0].transAxes)
    TextStr = output + '(' + ds.series[output]['Attr']['units'] + ')'
    ts_axes[0].text(0.85, 0.85, TextStr, color='r', horizontalalignment='right', transform=ts_axes[0].transAxes)
    for ThisOne, i in zip(drivers, range(1, pd["nDrivers"] + 1)):
        this_bottom = pd["ts_bottom"] + i*pd["ts_height"]
        rect = [pd["margin_left"], this_bottom, pd["ts_width"], pd["ts_height"]]
        ts_axes.append(plt.axes(rect, sharex=ts_axes[0]))
        data, flag, attr = pfp_utils.GetSeriesasMA(ds, ThisOne, si=si, ei=ei)
        data_notgf = numpy.ma.masked_where(flag != 0, data)
        data_gf = numpy.ma.masked_where(flag == 0, data)
        ts_axes[i].plot(xdt, data_notgf, 'b-')
        ts_axes[i].plot(xdt, data_gf, 'r-')
        plt.setp(ts_axes[i].get_xticklabels(), visible=False)
        TextStr = ThisOne + '(' + ds.series[ThisOne]['Attr']['units'] + ')'
        ts_axes[i].text(0.05, 0.85, TextStr, color='b', horizontalalignment='left', transform=ts_axes[i].transAxes)
    # save a hard copy of the plot
    sdt = xdt[0].strftime("%Y%m%d")
    edt = xdt[-1].strftime("%Y%m%d")
    if not os.path.exists(ieli["plot_path"]):
        os.makedirs(ieli["plot_path"])
    figname = (ieli["plot_path"] + pd["site_name"].replace(" ","") +
               "_" + mode + "_" + pd["label"])
    figname = figname + "_" + sdt + "_" + edt + '.png'
    fig.savefig(figname, format='png')
    # draw the plot on the screen
    if iel["gui"]["show_plots"]:
        plt.draw()
        pfp_utils.mypause(1)
        plt.ioff()
    else:
        plt.close(fig)
        plt.ion()
    return