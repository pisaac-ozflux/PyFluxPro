import datetime
import logging
import math
import os
import warnings
# 3rd party
import matplotlib
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    matplotlib.rcParams['toolbar'] = 'toolmanager'
import matplotlib.dates as mdt
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from mpl_toolkits.axes_grid1 import make_axes_locatable
from matplotlib.backend_tools import ToolToggleBase
import numpy
from scipy import stats
import statsmodels.api as sm
# PFP modules
from scripts import constants as c
from scripts import pfp_ck
from scripts import pfp_io
from scripts import pfp_utils

logger = logging.getLogger("pfp_log")

class XYPlotButton(ToolToggleBase):
    default_toggled = False
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    def enable(self, event):
        pass
    def disable(self, event):
        pass

def checktimestamps_plots(df, sheet, l1_info):
    # timestamp from data frame index
    dt = df.index.values
    # time step in minutes
    ddt = numpy.diff(dt).astype('timedelta64[s]').astype(int)/60
    bins = [0, 30, 60, 180, 1440, 10*1440, 30*1440, 90*1440]
    bin_labels = ["<30\nminutes", "30 to 60\nminutes", "60 to 180\nminutes",
                  "3 hrs to\n1 day", "1 to 10\ndays", "10 to 30\ndays", "30 to 90\ndays"]
    bin_ticks = [0, 1, 2, 3, 4, 5, 6]
    hist, bin_edges = numpy.histogram(ddt, bins=bins)
    hist[0] = hist[0]//2

    site_name = l1_info["read_excel"]["Global"]["site_name"]
    start = numpy.datetime_as_string(dt[0], unit='D')
    end = numpy.datetime_as_string(dt[-1], unit='D')
    title = site_name + ": " + sheet + "; " + start + " to " + end

    # turn on interactive plotting
    show_plots = l1_info["read_excel"]["Options"]["show_plots"]
    if show_plots.lower() == "yes":
        plt.ion()
    else:
        current_backend = plt.get_backend()
        plt.switch_backend("agg")
        plt.ioff()
    fig, axs = plt.subplots(nrows=1, ncols=2, figsize=(12, 6), width_ratios=[2, 1])
    fig.suptitle(title)
    axs[0].plot(dt[1:], ddt, 'b-')
    axs[0].set_xlabel("Date")
    axs[0].set_ylabel("Time step (minutes)")
    axs[1].bar(bin_ticks, hist)
    axs[1].set_xticks(bin_ticks, bin_labels, rotation=45)
    for i in range(len(bin_ticks)):
        axs[1].text(bin_ticks[i], hist[i], str(hist[i]), ha='center', va='bottom')
    axs[1].set_ylabel("Number")
    fig.tight_layout()
    # get the plot path
    plot_path = l1_info["read_excel"]["Files"]["plot_path"]
    # get the plot file name
    file_name = "timestamps_" + sheet + "_" + start + "_" + end + ".png"
    # get the plot file uri
    file_uri = os.path.join(plot_path, file_name)
    # save the plot as a PNG file
    fig.savefig(file_uri, format='png')
    # interactive or batch?
    if show_plots.lower() == "yes":
        # interactive so render the plot, pause 0.5 seconds, turn interactive plotting off
        plt.draw()
        pfp_utils.mypause(0.5)
        plt.ioff()
    else:
        # batch so close the figure, switch to previous backend
        plt.close(fig)
        plt.switch_backend(current_backend)
        plt.ion()
    return

def get_diurnalstats(DecHour,Data,dt):
    nInts = 24*int((60/dt)+0.5)
    Hr = numpy.array([c.missing_value]*nInts,dtype=numpy.float64)
    Av = numpy.array([c.missing_value]*nInts,dtype=numpy.float64)
    Sd = numpy.array([c.missing_value]*nInts,dtype=numpy.float64)
    Mx = numpy.array([c.missing_value]*nInts,dtype=numpy.float64)
    Mn = numpy.array([c.missing_value]*nInts,dtype=numpy.float64)
    for i in range(nInts):
        Hr[i] = float(i)*dt/60.
        li = numpy.where((abs(DecHour-Hr[i])<c.eps)&(abs(Data-float(c.missing_value))>c.eps))
        if numpy.size(li)!=0:
            Av[i] = numpy.mean(Data[li])
            Sd[i] = numpy.std(Data[li])
            Mx[i] = numpy.max(Data[li])
            Mn[i] = numpy.min(Data[li])
    return Hr, Av, Sd, Mx, Mn

def get_ticks(start, end):
    from datetime import timedelta as td
    delta = end - start

    if delta <= td(minutes=10):
        loc = mdt.MinuteLocator()
        fmt = mdt.DateFormatter('%H:%M')
    elif delta <= td(minutes=30):
        loc = mdt.MinuteLocator(byminute=list(range(0,60,5)))
        fmt = mdt.DateFormatter('%H:%M')
    elif delta <= td(hours=1):
        loc = mdt.MinuteLocator(byminute=list(range(0,60,15)))
        fmt = mdt.DateFormatter('%H:%M')
    elif delta <= td(hours=6):
        loc = mdt.HourLocator()
        fmt = mdt.DateFormatter('%H:%M')
    elif delta <= td(days=1):
        loc = mdt.HourLocator(byhour=list(range(0,24,3)))
        fmt = mdt.DateFormatter('%H:%M')
    elif delta <= td(days=3):
        loc = mdt.HourLocator(byhour=list(range(0,24,12)))
        fmt = mdt.DateFormatter('%d/%m %H')
    elif delta <= td(weeks=2):
        loc = mdt.DayLocator()
        fmt = mdt.DateFormatter('%d/%m')
    elif delta <= td(weeks=12):
        loc = mdt.WeekdayLocator()
        fmt = mdt.DateFormatter('%d/%m')
    elif delta <= td(weeks=104):
        loc = mdt.MonthLocator()
        fmt = mdt.DateFormatter('%d/%m')
    elif delta <= td(weeks=208):
        loc = mdt.MonthLocator(interval=3)
        fmt = mdt.DateFormatter('%d/%m/%y')
    else:
        loc = mdt.MonthLocator(interval=6)
        fmt = mdt.DateFormatter('%d/%m/%y')
    return loc,fmt

def get_yarray(ds,ThisOne):
    yarray = numpy.ma.masked_where(abs(ds.root["Variables"][ThisOne]['Data']-float(c.missing_value))<c.eps,
                                        ds.root["Variables"][ThisOne]['Data'])
    nRecs = numpy.ma.size(yarray)
    nNotM = numpy.ma.count(yarray)
    nMskd = numpy.ma.count_masked(yarray)
    if numpy.ma.count(yarray)==0:
        yarray = numpy.ma.zeros(numpy.size(yarray))
    return yarray,nRecs,nNotM,nMskd

def get_yaxislimitsfromcf(cf, nFig, maxkey, minkey, nSer, YArray):
    # Y axis maxima specified
    if maxkey in list(cf['Plots'][str(nFig)].keys()):
        # Evaluate the minima list
        maxlist = pfp_utils.string_to_list(cf['Plots'][str(nFig)][maxkey])
        # This entry is 'Auto' ...
        if str(maxlist[nSer])=='Auto':
            # ... so take the array minimum value
            YAxMax = numpy.ma.max(YArray)
        else:
            # Evaluate the entry for this series
            YAxMax = float(maxlist[nSer])
    else:
        # Y axis minima not given, use auto
        YAxMax = numpy.ma.max(YArray)
    # Y axis minima specified
    if minkey in list(cf['Plots'][str(nFig)].keys()):
        # Evaluate the minima list
        minlist = pfp_utils.string_to_list(cf['Plots'][str(nFig)][minkey])
        # This entry is 'Auto' ...
        if str(minlist[nSer])=='Auto':
             # ... so take the array minimum value
            YAxMin = numpy.ma.min(YArray)
        else:
            # Evaluate the entry for this series
            YAxMin = float(minlist[nSer])
    else:
        # Y axis minima not given, use auto
        YAxMin = numpy.ma.min(YArray)
    if (abs(YAxMax-YAxMin) < c.eps):
        YAxDelta = 0.001*YAxMax
        if YAxDelta == 0:
            YAxDelta = 1
        YAxMax = YAxMax + YAxDelta
        YAxMin = YAxMin - YAxDelta
    return YAxMax,YAxMin

def plot_fcvsustar_annual(ds):
    """
    Purpose:
     Plots Fc versus u* for each year and for each season
     (summer=DJF, autumn=MAM, winter=JJA, spring=SON) in
     each year.
    """
    site_name = ds.root["Attributes"]["site_name"]
    ts = int(float(ds.root["Attributes"]["time_step"]))
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    nbins = 20
    # plot each year
    plt.ion()
    start_year = ldt["Data"][0].year
    end_year = ldt["Data"][-1].year
    logger.info(" Doing annual Fc versus u* plots")
    for year in range(start_year, end_year+1):
        # get the start and end datetimes
        start = datetime.datetime(year, 1, 1, 0, 30, 0)
        end = datetime.datetime(year+1, 1, 1, 0, 0, 0)
        # get the variables from the data structure
        Fco2 = pfp_utils.GetVariable(ds, "Fco2", start=start, end=end)
        Fsd = pfp_utils.GetVariable(ds, "Fsd", start=start, end=end)
        ustar = pfp_utils.GetVariable(ds, "ustar", start=start, end=end)
        Ta = pfp_utils.GetVariable(ds, "Ta", start=start, end=end)
        # get the observations and night time filters
        obs = (Fco2["Flag"] == 0) & (ustar["Flag"] == 0)
        night = (Fsd["Data"] <= 10)
        obs_night_filter = obs & night
        # mask anything that is not an observation and at night
        ustar["Data"] = numpy.ma.masked_where(obs_night_filter == False, ustar["Data"])
        Fco2["Data"] = numpy.ma.masked_where(obs_night_filter == False, Fco2["Data"])
        Ta["Data"] = numpy.ma.masked_where(obs_night_filter == False, Ta["Data"])
        # get mask when either ustar or Fc or Ta masked
        mask = numpy.ma.mask_or(numpy.ma.getmaskarray(ustar["Data"]),
                                numpy.ma.getmaskarray(Fco2["Data"]))
        mask = numpy.ma.mask_or(mask, numpy.ma.getmaskarray(Ta["Data"]))
        # apply mask
        ustar["Data"] = numpy.ma.masked_where(mask == True, ustar["Data"])
        Fco2["Data"] = numpy.ma.masked_where(mask == True, Fco2["Data"])
        Ta["Data"] = numpy.ma.masked_where(mask == True, Ta["Data"])
        # remove masked elements
        ustar["Data"] = numpy.ma.compressed(ustar["Data"])
        Fco2["Data"] = numpy.ma.compressed(Fco2["Data"])
        Ta["Data"] = numpy.ma.compressed(Ta["Data"])
        # get the binned statistics
        count, edges, numbers = stats.binned_statistic(ustar["Data"],Fco2["Data"],
                                                       statistic='count', bins=nbins)
        means, edges, numbers = stats.binned_statistic(ustar["Data"],Fco2["Data"],
                                                       statistic='mean', bins=nbins)
        stdevs, edges, numbers = stats.binned_statistic(ustar["Data"],Fco2["Data"],
                                                        statistic='std', bins=nbins)
        mids = (edges[:-1]+edges[1:])/2
        # drop bins with less than 10 counts
        mids = numpy.array(mids[count >= 10])
        means = numpy.array(means[count >= 10])
        stdevs = numpy.array(stdevs[count >= 10])
        # do the plot
        fig, axs = plt.subplots(nrows=1, ncols=1, figsize=(6, 6))
        fig.canvas.manager.set_window_title("Fco2 versus u*: "+str(year))
        axs.scatter(ustar["Data"], Fco2["Data"], c=Ta["Data"], alpha=0.25, s=10)
        axs.errorbar(mids, means, yerr=stdevs, fmt='ro')
        axs.set_xlabel("u* ("+ustar["Attr"]["units"]+")")
        axs.set_ylabel("Fco2 ("+Fco2["Attr"]["units"]+")")
        if len(means) > 0:
            axs.set_ylim([min(means-stdevs), max(means+stdevs)])
        axs.set_title(site_name+": "+str(year))
        plt.draw()
        pfp_utils.mypause(0.5)
    return

def plot_fcvsustar_seasonal(ds):
    site_name = ds.root["Attributes"]["site_name"]
    ts = int(float(ds.root["Attributes"]["time_step"]))
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    nbins = 20
    # plot each season for each year
    plt.ion()
    start_year = ldt["Data"][0].year
    end_year = ldt["Data"][-1].year
    # plot 4 seasons for each year
    logger.info(" Doing seasonal Fco2 versus u* plots")
    nrows = 2
    ncols = 2
    for year in range(start_year, end_year+1):
        fig, axs = plt.subplots(nrows=nrows, ncols=ncols, figsize=(8, 8))
        fig.canvas.manager.set_window_title("Fco2 versus u*: "+str(year))
        for n, season in enumerate(["Summer", "Autumn", "Winter", "Spring"]):
            col = numpy.mod(n, ncols)
            row = n//ncols
            if season == "Summer":
                start = datetime.datetime(year-1, 12, 1, 0, 0, 0) + datetime.timedelta(minutes=ts)
                end = datetime.datetime(year, 3, 1, 0, 0, 0)
            elif season == "Autumn":
                start = datetime.datetime(year, 3, 1, 0, 0, 0) + datetime.timedelta(minutes=ts)
                end = datetime.datetime(year, 6, 1, 0, 0, 0)
            elif season == "Winter":
                start = datetime.datetime(year, 6, 1, 0, 0, 0) + datetime.timedelta(minutes=ts)
                end = datetime.datetime(year, 9, 1, 0, 0, 0)
            elif season == "Spring":
                start = datetime.datetime(year, 9, 1, 0, 0, 0) + datetime.timedelta(minutes=ts)
                end = datetime.datetime(year, 12, 1, 0, 0, 0)
            if (end < ldt["Data"][0]) or (start > ldt["Data"][-1]):
                fig.delaxes(axs[row, col])
                continue
            # get the variables from the data structure
            Fco2 = pfp_utils.GetVariable(ds, "Fco2", start=start, end=end)
            Fsd = pfp_utils.GetVariable(ds, "Fsd", start=start, end=end)
            ustar = pfp_utils.GetVariable(ds, "ustar", start=start, end=end)
            Ta = pfp_utils.GetVariable(ds, "Ta", start=start, end=end)
            # get the observations and night time filters
            obs = (Fco2["Flag"] == 0) & (ustar["Flag"] == 0)
            night = (Fsd["Data"] <= 10)
            obs_night_filter = obs & night
            # mask anything that is not an observation and at night
            ustar["Data"] = numpy.ma.masked_where(obs_night_filter == False, ustar["Data"])
            Fco2["Data"] = numpy.ma.masked_where(obs_night_filter == False, Fco2["Data"])
            Ta["Data"] = numpy.ma.masked_where(obs_night_filter == False, Ta["Data"])
            # get mask when either ustar or Fc or Ta masked
            mask = numpy.ma.mask_or(numpy.ma.getmaskarray(ustar["Data"]),
                                    numpy.ma.getmaskarray(Fco2["Data"]))
            mask = numpy.ma.mask_or(mask, numpy.ma.getmaskarray(Ta["Data"]))
            # apply mask
            ustar["Data"] = numpy.ma.masked_where(mask == True, ustar["Data"])
            Fco2["Data"] = numpy.ma.masked_where(mask == True, Fco2["Data"])
            Ta["Data"] = numpy.ma.masked_where(mask == True, Ta["Data"])
            # remove masked elements
            ustar["Data"] = numpy.ma.compressed(ustar["Data"])
            Fco2["Data"] = numpy.ma.compressed(Fco2["Data"])
            Ta["Data"] = numpy.ma.compressed(Ta["Data"])
            # if no data, skip this plot and delete the axes
            if (len(ustar["Data"]) == 0) or (len(Fco2["Data"]) == 0) or (len(Ta["Data"]) == 0):
                fig.delaxes(axs[row, col])
                continue
            # get the binned statistics
            count, edges, numbers = stats.binned_statistic(ustar["Data"],Fco2["Data"],
                                                           statistic='count', bins=nbins)
            means, edges, numbers = stats.binned_statistic(ustar["Data"],Fco2["Data"],
                                                           statistic='mean', bins=nbins)
            stdevs, edges, numbers = stats.binned_statistic(ustar["Data"],Fco2["Data"],
                                                            statistic='std', bins=nbins)
            mids = (edges[:-1]+edges[1:])/2
            # drop bins with less than 10 counts
            mids = numpy.array(mids[count >= 10])
            means = numpy.array(means[count >= 10])
            stdevs = numpy.array(stdevs[count >= 10])
            axs[row, col].scatter(ustar["Data"], Fco2["Data"], c=Ta["Data"], alpha=0.25, s=10)
            axs[row, col].errorbar(mids, means, yerr=stdevs, fmt='ro')
            axs[row, col].set_title(site_name+": "+str(year)+" "+season)
            axs[row, col].set_xlabel("u* ("+ustar["Attr"]["units"]+")")
            axs[row, col].set_ylabel("Fco2 ("+Fco2["Attr"]["units"]+")")
            if len(means) > 0:
                axs[row, col].set_ylim([min(means-stdevs), max(means+stdevs)])
        fig.tight_layout()
        plt.draw()
        pfp_utils.mypause(0.5)
    plt.ioff()
    return

def plot_fcvsustar_monthly(ds):
    site_name = ds.root["Attributes"]["site_name"]
    ts = int(float(ds.root["Attributes"]["time_step"]))
    dt = pfp_utils.GetVariable(ds, "DateTime")
    nbins = 20
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    # plot each month for each year
    plt.ion()
    start_year = dt["Data"][0].year
    end_year = dt["Data"][-1].year
    # plot 12 months for each year
    logger.info(" Doing monthly Fco2 versus u* plots")
    nrows = 4
    ncols = 3
    for year in range(start_year, end_year+1):
        start = datetime.datetime(year, 1, 1, 0, 0, 0) + datetime.timedelta(minutes=ts)
        end = datetime.datetime(year+1, 1, 1, 0, 0, 0)
        # get the variables from the data structure
        ldt = pfp_utils.GetVariable(ds, "DateTime", start=start, end=end)
        month = numpy.array([d.month for d in ldt["Data"]])
        Fco2 = pfp_utils.GetVariable(ds, "Fco2", start=start, end=end)
        Fsd = pfp_utils.GetVariable(ds, "Fsd", start=start, end=end)
        ustar = pfp_utils.GetVariable(ds, "ustar", start=start, end=end)
        Ta = pfp_utils.GetVariable(ds, "Ta", start=start, end=end)
        # get the figure
        fig, axs = plt.subplots(nrows=nrows, ncols=ncols, figsize=(8, 10))
        fig.canvas.manager.set_window_title("Fco2 versus u*: "+str(year))
        # loop over months
        for n, m in enumerate([12] + list(range(1, 12))):
            ncol = numpy.mod(n, ncols)
            nrow = n//ncols
            #if (end < dt["Data"][0]) or (start > dt["Data"][-1]):
                #fig.delaxes(axs[nrow, ncol])
                #continue
            # get indices for this month
            idx = numpy.where(month == m)[0]
            # skip month and remove axes if there is no data for this month
            if len(idx) == 0:
                axs[nrow, ncol].remove()
                continue
            # get the observations and night time filters
            obs = (Fco2["Flag"][idx] == 0) & (ustar["Flag"][idx] == 0)
            night = (Fsd["Data"][idx] <= 10)
            obs_night_filter = obs & night
            # mask anything that is not an observation and at night
            us = numpy.ma.masked_where(obs_night_filter == False, ustar["Data"][idx])
            fc = numpy.ma.masked_where(obs_night_filter == False, Fco2["Data"][idx])
            ta = numpy.ma.masked_where(obs_night_filter == False, Ta["Data"][idx])
            # get mask when either ustar or Fco2 or Ta masked
            mask = numpy.ma.mask_or(numpy.ma.getmaskarray(us),
                                    numpy.ma.getmaskarray(fc))
            mask = numpy.ma.mask_or(mask, numpy.ma.getmaskarray(ta))
            # apply mask
            us = numpy.ma.masked_where(mask == True, us)
            fc = numpy.ma.masked_where(mask == True, fc)
            ta = numpy.ma.masked_where(mask == True, ta)
            # remove masked elements
            us = numpy.ma.compressed(us)
            fc = numpy.ma.compressed(fc)
            ta = numpy.ma.compressed(ta)
            # if no data, skip this plot and delete the axes
            if (len(us) == 0) or (len(fc) == 0) or (len(ta) == 0):
                fig.delaxes(axs[nrow, ncol])
                continue
            # get the binned statistics
            count, edges, numbers = stats.binned_statistic(us, fc, statistic='count', bins=nbins)
            means, edges, numbers = stats.binned_statistic(us, fc, statistic='mean', bins=nbins)
            stdevs, edges, numbers = stats.binned_statistic(us, fc, statistic='std', bins=nbins)
            mids = (edges[:-1]+edges[1:])/2
            # drop bins with less than 10 counts
            mids = numpy.array(mids[count >= 3])
            means = numpy.array(means[count >= 3])
            stdevs = numpy.array(stdevs[count >= 3])
            axs[nrow, ncol].scatter(us, fc, c=ta, alpha=0.25, s=10)
            axs[nrow, ncol].errorbar(mids, means, yerr=stdevs, fmt='ro')
            axs[nrow, ncol].set_title(site_name+": "+str(year)+" "+months[m-1])
            axs[nrow, ncol].set_xlabel("u* ("+ustar["Attr"]["units"]+")")
            axs[nrow, ncol].set_ylabel("Fco2 ("+Fco2["Attr"]["units"]+")")
            if len(means) > 0:
                axs[nrow, ncol].set_ylim([min(means-stdevs), max(means+stdevs)])
        fig.tight_layout()
        plt.draw()
        pfp_utils.mypause(0.5)
    plt.ioff()
    return

def pltfingerprint_createdict(cf,ds):
    fp_info = {}
    fp_info["general"] = {}
    fp_info["variables"] = {}
    # parse the control file to get the information for the fingerprint plot
    for var in cf["Variables"]:
        # create the dictionary for this variable
        fp_info["variables"][var] = {}
        # get the input filename
        if "in_filename" in cf["Variables"][var]:
            fp_info["variables"][var]["in_filename"] = str(cf["Variables"][var]["in_filename"])
        else:
            fp_info["variables"][var]["in_filename"] = pfp_io.get_infilenamefromcf(cf)
        # get the variable name
        if "name" in cf["Variables"][var]:
            fp_info["variables"][var]["name"] = str(cf["Variables"][var]["name"])
        else:
            fp_info["variables"][var]["name"] = str(var)
        # get the upper and lower range limits
        if "lower" in cf["Variables"][var]:
            fp_info["variables"][var]["lower"] = float(cf["Variables"][var]["lower"])
        else:
            fp_info["variables"][var]["lower"] = float(-1)*c.large_value
        if "upper" in cf["Variables"][var]:
            fp_info["variables"][var]["upper"] = float(cf["Variables"][var]["upper"])
        else:
            fp_info["variables"][var]["upper"] = c.large_value
    # get the start and end datetimes for all files and find the overlap period
    var_list = list(fp_info["variables"].keys())
    ds_0 = ds[fp_info["variables"][var_list[0]]["in_filename"]]
    fp_info["variables"][var_list[0]]["time_coverage_start"] = ds_0.root["Variables"]["DateTime"]["Data"][0]
    fp_info["variables"][var_list[0]]["time_coverage_end"] = ds_0.root["Variables"]["DateTime"]["Data"][-1]
    fp_info["general"]["overlap_start"] = fp_info["variables"][var_list[0]]["time_coverage_start"]
    fp_info["general"]["overlap_end"] = fp_info["variables"][var_list[0]]["time_coverage_end"]
    fp_info["variables"][var_list[0]]["nc_nrecs"] = int(ds_0.root["Attributes"]["nc_nrecs"])
    fp_info["variables"][var_list[0]]["site_name"] = str(ds_0.root["Attributes"]["site_name"])
    fp_info["variables"][var_list[0]]["processing_level"] = str(ds_0.root["Attributes"]["processing_level"])
    fp_info["variables"][var_list[0]]["time_step"] = int(float(ds_0.root["Attributes"]["time_step"]))
    if len(var_list)>1:
        for var in var_list[1:]:
            ds_n = ds[fp_info["variables"][var]["in_filename"]]
            fp_info["variables"][var]["time_coverage_start"] = ds_n.root["Variables"]["DateTime"]["Data"][0]
            fp_info["variables"][var]["time_coverage_end"] = ds_n.root["Variables"]["DateTime"]["Data"][-1]
            fp_info["variables"][var]["nc_nrecs"] = int(ds_n.root["Attributes"]["nc_nrecs"])
            fp_info["variables"][var]["site_name"] = str(ds_n.root["Attributes"]["site_name"])
            fp_info["variables"][var]["processing_level"] = str(ds_n.root["Attributes"]["processing_level"])
            fp_info["variables"][var]["time_step"] = int(float(ds_n.root["Attributes"]["time_step"]))
            # get the start and end datetimes where the files overlap
            fp_info["general"]["overlap_start"] = max([fp_info["general"]["overlap_start"],fp_info["variables"][var]["time_coverage_start"]])
            fp_info["general"]["overlap_end"] = min([fp_info["general"]["overlap_end"],fp_info["variables"][var]["time_coverage_end"]])
    return fp_info

def pltfingerprint_readncfiles(cf):
    ds = {}
    if "Files" in cf:
        infilename = pfp_io.get_infilenamefromcf(cf)
        ds[infilename] = pfp_io.NetCDFRead(infilename)
    for var in list(cf["Variables"].keys()):
        if "in_filename" in cf["Variables"][var]:
            if cf["Variables"][var]["in_filename"] not in ds:
                infilename = cf["Variables"][var]["in_filename"]
                ds[cf["Variables"][var]["in_filename"]] = pfp_io.NetCDFRead(infilename)
                if ds[cf["Variables"][var]["in_filename"]].info["returncodes"]["value"] != 0: return ds
    return ds

def plot_fingerprint(cf):
    """ Do a fingerprint plot"""
    # set up some variable aliases
    aliases = {"CO2":["CO2", "Cc"], "Cc":["Cc", "CO2"],
               "H2O":["H2O", "AH"], "AH":["AH", "H2O"]}
    # read the input files
    ds = pltfingerprint_readncfiles(cf)
    # create a dictionary to hold the fingerprint plot information
    fp_info = pltfingerprint_createdict(cf,ds)
    overlap_start = fp_info["general"]["overlap_start"]
    overlap_end = fp_info["general"]["overlap_end"]
    # get a list of site names and remove duplicates
    var_list = list(fp_info["variables"].keys())
    site_name_list = [fp_info["variables"][var]["site_name"] for var in var_list]
    site_name_list = list(set(site_name_list))
    site_name = ','.join(str(x) for x in site_name_list)
    # do the same for processing levels
    level_list = [fp_info["variables"][var]["processing_level"] for var in var_list]
    level_list = list(set(level_list))
    level = ','.join(str(x) for x in level_list)
    title_str = site_name+' '+level
    title_str = title_str+' from '+str(overlap_start)+' to '+str(overlap_end)
    # loop over plots
    show_plots = pfp_utils.get_optionskeyaslogical(cf, "show_plots", default=True)
    for nFig, title in enumerate(cf["Plots"].keys()):
        if show_plots:
            plt.ion()
        else:
            current_backend = plt.get_backend()
            plt.switch_backend("agg")
            plt.ioff()
        fig = plt.figure(nFig, figsize=(13,8))
        fig.clf()
        fig.canvas.manager.set_window_title(title)
        plt.figtext(0.5, 0.95, title_str, horizontalalignment="center")
        fig_var_list = pfp_utils.string_to_list(cf["Plots"][title]["variables"])
        logger.info(" Plotting fingerprint: " + str(fig_var_list))
        nPlots = len(fig_var_list)
        n = 0
        for var in fig_var_list:
            nc_varname = fp_info["variables"][var]["name"]
            infilename = fp_info["variables"][var]["in_filename"]
            ldt = ds[infilename].root["Variables"]["DateTime"]["Data"]
            ts = fp_info["variables"][var]["time_step"]
            si = pfp_utils.GetDateIndex(ldt, str(overlap_start), ts=ts, default=0, match='startnextday')
            ei = pfp_utils.GetDateIndex(ldt, str(overlap_end), ts=ts, default=-1, match='endpreviousday')
            ldt = ldt[si:ei + 1]
            nPerHr = int(float(60)/ts + 0.5)
            nPerDay = int(float(24)*nPerHr + 0.5)
            nDays = len(ldt)//nPerDay
            # let's check the named variable is in the data structure
            if nc_varname not in list(ds[infilename].root["Variables"].keys()):
                # if it isn't, let's look for an alias
                if nc_varname in list(aliases.keys()):
                    found_alias = False
                    for alias in aliases[nc_varname]:
                        if alias in list(ds[infilename].root["Variables"].keys()):
                            nc_varname = alias
                            found_alias = True
                    if not found_alias:
                        msg = " Variable "+nc_varname+" not found in data structure, skipping ..."
                        logger.warning(msg)
                        continue
                else:
                    msg = " No alias found for "+nc_varname+", skipping ..."
                    logger.warning(msg)
                    continue
            obs = pfp_utils.GetVariable(ds[infilename], nc_varname, start=si, end=ei)
            data = pfp_ck.cliptorange(obs["Data"],
                                      fp_info["variables"][var]["lower"],
                                      fp_info["variables"][var]["upper"])
            data_daily = data.reshape(nDays,nPerDay)
            units = str(ds[infilename].root["Variables"][nc_varname]['Attr']['units'])
            label = var + ' (' + units + ')'
            if n == 0:
                ax = plt.subplot(1,nPlots,n+1)
            else:
                ax = plt.subplot(1,nPlots,n+1,sharey=ax)
            sd = mdt.date2num(ldt[0])
            ed = mdt.date2num(ldt[-1])
            # only plot the fingerprint if there is data to plot
            if numpy.ma.count(data) != 0:
                plt.imshow(data_daily,extent=[0,24,sd,ed],aspect='auto',origin='lower',interpolation="none")
                ax.yaxis_date()
                cb = plt.colorbar(orientation='horizontal',fraction=0.02,pad=0.075)
                if numpy.ma.min(data) == numpy.ma.max(data):
                    if numpy.min(data)!=0:
                        data_min = numpy.ma.min(data)-0.01*numpy.ma.min(data)
                        data_max = numpy.ma.max(data)+0.01*numpy.ma.max(data)
                    else:
                        data_min = -1.0
                        data_max = 1.0
                else:
                    data_min = numpy.ma.min(data)
                    data_max = numpy.ma.max(data)
                cb.set_ticks(numpy.linspace(data_min,data_max,4))
            plt.xticks([0,6,12,18,24])
            plt.xlabel(label)
            if n != 0:
                plt.setp(ax.get_yticklabels(), visible=False)
            n += 1
        plot_path = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="./plots/")
        plot_path = os.path.join(plot_path, "fingerprints", "")
        if not os.path.exists(plot_path):
            os.makedirs(plot_path)
        pngname = plot_path + site_name.replace(" ","") + "_" + level + "_"
        pngname = pngname + title.replace(" ", "_") + ".png"
        fig.savefig(pngname, format="png")
        if show_plots:
            plt.draw()
            pfp_utils.mypause(0.5)
            plt.ioff()
        else:
            plt.close(fig)
            plt.switch_backend(current_backend)
            plt.ion()

def plot_fluxnet(cf):
    """ Plot the FluxNet style plots. """

    series_list = list(cf["Variables"].keys())
    infilename = pfp_io.get_infilenamefromcf(cf)

    ds = pfp_io.NetCDFRead(infilename)
    if ds.info["returncodes"]["value"] != 0: return
    site_name = ds.root["Attributes"]["site_name"]
    ldt=ds.root["Variables"]["DateTime"]["Data"]
    sdt = ldt[0]
    edt = ldt[-1]
    nFig = 0
    plt.ion()
    for series in series_list:
        if "name" in cf["Variables"][series]:
            label = cf["Variables"][series]["name"]
        else:
            label = series
        if label not in ds.root["Variables"].keys():
            logger.error("Series " + label + " not found in input file, skipping ...")
            continue
        logger.info(" Doing plot for " + label)
        var = pfp_utils.GetVariable(ds, label)
        nFig = nFig + 1
        fig = plt.figure(nFig,figsize=(10.9, 7.5))
        fig.canvas.manager.set_window_title(label)
        plt.plot(ldt, var["Data"], "b.")
        plt.xlim(sdt, edt)
        plt.xlabel("Date")
        plt.ylabel(label + " (" + var["Attr"]["units"] + ")")
        title_str = site_name + ": " + sdt.strftime("%Y-%m-%d") + " to "
        title_str += edt.strftime("%Y-%m-%d") + "; " + series
        plt.title(title_str)
        figname = 'plots/' + ds.root["Attributes"]['site_name'].replace(' ','')
        figname += '_' + ds.root["Attributes"]['processing_level'] + '_FC_' + label + '.png'
        fig.savefig(figname, format='png')
        plt.draw()
        pfp_utils.mypause(0.5)
    plt.ioff()
    return

def plot_explore_fingerprints(ds, selections):
    """
    Purpose:
     Plot fingerprints of variables selected by the user from the GUI
     when using the File/Explore feature.
    Usage:
    Side effects:
    Author: PRI
    Date: April 2020
    """
    groups = sorted(list(selections.keys()))
    labels = []
    for group in groups:
        labels += selections[group]
    msg = " Plotting fingerprint for " + ", ".join(labels)
    logger.info(msg)
    site_name = ds.root["Attributes"]["site_name"]
    # number of columns, each column will be 1 fingerprint
    ncols = len(labels)
    # create the figure
    plt.ion()
    fig, axs = plt.subplots(ncols=ncols, sharey=True, figsize=(7.5, 10.9))
    # axs must be a list
    if ncols == 1: axs = [axs]
    fig.subplots_adjust(wspace=0.05, hspace=0.05, left=0.1, right=0.95, top=0.95, bottom=0.1)
    # put a title on the figure window
    fig.canvas.manager.set_window_title(site_name)
    n = 0
    for group in groups:
        gattr = getattr(ds, group)["Attributes"]
        # get the time step
        ts = int(float(gattr["time_step"]))
        # get the start and end dates for whole days
        dt = pfp_utils.GetVariable(ds, "DateTime", group=group)
        si = pfp_utils.GetDateIndex(dt["Data"], dt["Data"][0], ts=ts,
                                    default=0, match='startnextday')
        ei = pfp_utils.GetDateIndex(dt["Data"], dt["Data"][-1], ts=ts,
                                    default=-1, match='endpreviousday')
        # subset the datetime to whole days
        ldt = dt["Data"][si:ei + 1]
        if n == 0:
            # put a title on the figure
            title_str = site_name + ": " + ldt[0].strftime("%Y-%m-%d") + " to "
            title_str += ldt[-1].strftime("%Y-%m-%d")
            fig.suptitle(title_str, fontsize=16)
        # get the number of records per day and the number of whole days
        nPerHr = int(float(60)/ts + 0.5)
        nPerDay = int(float(24)*nPerHr + 0.5)
        nDays = len(ldt)//nPerDay
        # loop over variables to be plotted
        for label in labels:
            # get the data
            var = pfp_utils.GetVariable(ds, label, group=group, start=si, end=ei)
            if numpy.ma.count(var["Data"]) == 0:
                msg = label + ": no data found, skipping..."
                logger.warning(msg)
                continue
            # reshape into a 2D array
            data_daily = var["Data"].reshape(nDays, nPerDay)
            # clip data to the 0.25 and 99.75 percentiles to suppress outliers
            # this helps make the colour scale even
            vmin = numpy.percentile(numpy.ma.compressed(data_daily), 0.25)
            vmax = numpy.percentile(numpy.ma.compressed(data_daily), 99.75)
            # get the start and end dates as numbers
            sd = mdt.date2num(ldt[0])
            ed = mdt.date2num(ldt[-1])
            # render the image
            im = axs[n].imshow(data_daily, extent=[0, 24, sd, ed], aspect='auto',
                               origin='lower', interpolation="none",
                               cmap="viridis", vmin=vmin, vmax=vmax)
            # add a colour bar
            divider = make_axes_locatable(axs[n])
            cax = divider.append_axes('bottom', size='1%', pad=0.5)
            fig.colorbar(im, cax=cax, orientation='horizontal')
            # do the major ticks on the Y (date) axis
            axs[n].yaxis_date()
            axs[n].yaxis.set_major_locator(mdt.YearLocator())
            axs[n].yaxis.set_major_formatter(mdt.DateFormatter('%Y'))
            # set the ticks on the X (hour) axis
            axs[n].set_xticks([0, 6, 12, 18, 24])
            # label the X axis
            xlabel = label + " (" + var["Attr"]["units"] + ")"
            axs[n].set_xlabel(xlabel)
            # suppress the Y axis labels if more than 1 image
            if n != 0:
                plt.setp(axs[n].get_yticklabels(), visible=False)
            n += 1
    # render the fingerprint
    plt.draw()
    # pause to let the image appear on the creen
    pfp_utils.mypause(0.5)
    # turn off interactive plotting mode
    plt.ioff()
    return

def plot_explore_histograms(ds, labels):
    """ Plot histograms of selected variables."""
    # set up a dictionary with the percentiles of the histograms to be plotted
    p = {0: {"lwr": 0.0, "upr": 100.0},
         1: {"lwr": 0.1, "upr": 99.9},
         2: {"lwr": 0.5, "upr": 99.5},
         3: {"lwr": 1.0, "upr": 99.0},
         4: {"lwr": 2.5, "upr": 97.5}}
    site_name = ds.root["Attributes"]["site_name"]
    plt.ion()
    for label in labels:
        var = pfp_utils.GetVariable(ds, label)
        sdt = var["DateTime"][0]
        edt = var["DateTime"][-1]
        fig = plt.figure(figsize=(11, 8), tight_layout=True)
        window_title = site_name + ": " + var["Label"]
        fig.canvas.manager.set_window_title(window_title)
        gs = gridspec.GridSpec(2, 5, height_ratios=[1, 0.5])
        ax_ts = fig.add_subplot(gs[0, :])
        title_str = site_name + ": " + sdt.strftime("%Y-%m-%d") + " to "
        title_str += edt.strftime("%Y-%m-%d")
        ax_ts.set_title(title_str)
        ax_ts.plot(var["DateTime"], var["Data"], 'b.', label=var["Label"])
        ax_ts.legend()
        for n in p:
            d = plot_explore_do_histogram(var, p[n]["lwr"], p[n]["upr"])
            lwrs = str(pfp_utils.round2significant(d["lwr"], 4))
            uprs = str(pfp_utils.round2significant(d["upr"], 4))
            x = numpy.arange(len(d["hist"]))
            ax_hist = fig.add_subplot(gs[1, n])
            label = str(p[n]["lwr"]) + "," + str(p[n]["upr"])
            ax_hist.bar(x, d["hist"])
            ax_hist.text(0.5, 0.9, label, transform=ax_hist.transAxes,
                        horizontalalignment='center')
            ax_hist.set_xticks([x[1], x[-2]])
            ax_hist.set_xticklabels([lwrs, uprs])
        plt.draw()
        pfp_utils.mypause(0.5)
    return

def plot_explore_do_histogram(var, plwr, pupr):
    """ Return a dictionary with the histogram results for given percentiles."""
    d = {}
    idx = numpy.where(numpy.ma.getmaskarray(var["Data"]) == False)[0]
    d["lwr"], d["upr"] = numpy.percentile(var["Data"][idx],[plwr, pupr])
    idx = numpy.ma.where((var["Data"] >= d["lwr"]) &
                         (var["Data"] <= d["upr"]))[0]
    bins = numpy.linspace(d["lwr"], d["upr"], num=25)
    bins = numpy.insert(bins, 0, numpy.ma.min(var["Data"]))
    d["bins"] = numpy.append(bins, numpy.ma.max(var["Data"]))
    d["hist"], d["edges"] = numpy.histogram(var["Data"][idx], bins=d["bins"])
    d["idx"] = idx
    return d

def plot_explore_percentiles(ds, selections):
    """ Plot time series histograms of selected variables."""
    p = {0: {"lwr": 0.0, "upr": 100.0},
         1: {"lwr": 0.1, "upr": 99.9},
         2: {"lwr": 0.5, "upr": 99.5},
         3: {"lwr": 1.0, "upr": 99.0},
         4: {"lwr": 2.5, "upr": 97.5}}
    site_name = ds.root["Attributes"]["site_name"]
    groups = sorted(list(selections.keys()))
    plt.ion()
    for group in groups:
        labels = selections[group]
        for label in labels:
            var = pfp_utils.GetVariable(ds, label, group=group)
            sdt = var["DateTime"][0]
            edt = var["DateTime"][-1]
            fig = plt.figure(figsize=(11, 8), tight_layout=True)
            window_title = site_name + ": " + var["Label"]
            fig.canvas.manager.set_window_title(window_title)
            gs = gridspec.GridSpec(5, 2, width_ratios=[5, 1])
            for n in p:
                d = plot_explore_do_histogram(var, p[n]["lwr"], p[n]["upr"])
                ax_ts = fig.add_subplot(gs[n, 0])
                if n == 0:
                    title_str = site_name + ": " + sdt.strftime("%Y-%m-%d") + " to "
                    title_str += edt.strftime("%Y-%m-%d") + "; " + label
                    ax_ts.set_title(title_str)
                legend = str(p[n]["lwr"]) + "," + str(p[n]["upr"])
                ax_ts.plot(var["DateTime"][d["idx"]], var["Data"][d["idx"]], 'b.', label=legend)
                ax_ts.legend()
                lwrs = str(pfp_utils.round2significant(d["lwr"], 4))
                uprs = str(pfp_utils.round2significant(d["upr"], 4))
                x = numpy.arange(len(d["hist"]))
                ax_hist = fig.add_subplot(gs[n, 1])
                hist_label = str(p[n]["lwr"]) + "," + str(p[n]["upr"])
                ax_hist.bar(x, d["hist"])
                ax_hist.text(0.5, 0.85, hist_label, transform=ax_hist.transAxes,
                             horizontalalignment='center')
                ax_hist.set_xticks([x[1], x[-2]])
                ax_hist.set_xticklabels([lwrs, uprs])
            plt.draw()
            pfp_utils.mypause(0.5)
    return

def plot_explore_timeseries(ds, selections):
    """ Plot time series of selected variables."""
    site_name = ds.root["Attributes"]["site_name"]
    groups = sorted(list(selections.keys()))
    nrows = 0
    for group in groups:
        nrows += len(selections[group])
    plt.ion()
    fig, axs = plt.subplots(nrows=nrows, sharex=True, figsize=(10.9, 7.5))
    fig.subplots_adjust(wspace=0.0, hspace=0.05, left=0.1, right=0.95, top=0.95, bottom=0.1)
    if nrows == 1: axs = [axs]
    fig.canvas.manager.set_window_title(site_name)
    n = 0
    for group in groups:
        labels = selections[group]
        for label in labels:
            var = pfp_utils.GetVariable(ds, label, group=group)
            count_str = " Total " + str(len(var["Data"])) + ", Usable "
            count_str += str(numpy.ma.count(var["Data"])) + " ("
            count_str += str(numpy.rint(100*numpy.ma.count(var["Data"])/len(var["Data"])))
            count_str += "%)"
            sdt = var["DateTime"][0]
            edt = var["DateTime"][-1]
            axs[n].plot(var["DateTime"], var["Data"], "b.", label=label+count_str)
            axs[n].legend()
            axs[n].set_xlim([sdt, edt])
            if n == 0:
                title_str = site_name + ": " + sdt.strftime("%Y-%m-%d") + " to "
                title_str += edt.strftime("%Y-%m-%d")
                axs[n].set_title(title_str)
            if n == nrows-1:
                axs[n].set_xlabel("Date")
            axs[n].set_ylabel("(" + var["Attr"]["units"] + ")")
            n += 1
    plt.draw()
    pfp_utils.mypause(0.5)
    plt.ioff()
    return

def plot_explore_timeseries_grouped(ds, selections):
    """
    Purpose:
     Plot time series of grouped variables.
    Special case:
     If the user selects only 2 variables, both with the same variable name prefix
     and then choses a "Grouped" time series then we add an option to produce an XY
     scatter plot when the user zooms into a part of the time series plot using the
     toolbar "Zoom" tool.  The steps are as follows:
     1) select 2 variables with the same variable name prefix e.g. AH_IRGA_Av and AH_HMP_80m
     2) choose "Plot time series/Grouped"
     3) an extra button labelled "XY" is added to the default toolbar for the figure
     4) click on the "XY" button to enable production of an XY
        scatter plot when the user zooms in on part of the plot
     5) click on the "Zoom" button
     6) whenever the user zooms into a region of the plot, an XY scatter
        plot of the 2 variables is produced for the date range covered by
        the zoomed view.
    Date: Back in the day
    Author: PRI
    Mods:
     December 2022 - added ability to plot XY scatter plot of 2 variables
                     when zoom tool used
    """
    # colours for the lines
    colors = ["blue","red","green","yellow","magenta","black","cyan","brown"]
    # site name for the title
    site_name = ds.root["Attributes"]["site_name"]
    # get the groups to be plotted
    groups = sorted(list(selections.keys()))
    # find all of the labels to be plotted
    all_labels = []
    for group in groups:
        all_labels += selections[group]
    # get the variable groups to be plotted
    label_groups = sorted(list(set([l.split("_")[0] for l in all_labels])))
    # which is also the number of rows in the plot
    nrows = len(label_groups)
    # now rearrange the variable group, netCDF group and variable labels into
    # a dictionary for convenience of plotting
    # d = {'ER': {'root': ['ER_LL', 'ER_LT', 'ER_SOLO']},
    #      'GPP': {'root': ['GPP_LL', 'GPP_LT', 'GPP_SOLO']},
    #      'NEE': {'root': ['NEE_LL', 'NEE_LT', 'NEE_SOLO']}}
    d = {}
    for lg in label_groups:
        d[lg] = {}
        gll = []
        for g in groups:
            for al in all_labels:
                if lg in al:
                    gll.append(al)
            d[lg][g] = gll
    # turn on interactive plotting
    plt.ion()
    # get a figure and axes with shared X axis, nrows is the number of groups being plotted
    fig, axs = plt.subplots(nrows=nrows, sharex=True, figsize=(10.9, 7.5))
    # if only 1 row is being plotted ...
    if nrows == 1:
        # put the axes object into a list, same as nrows > 1
        axs = [axs]
        # check to see if only 2 variables have been selected ...
        if len(all_labels) == 2:
            # if so then put an "XY" button in the toolbar
            fig.canvas.manager.toolmanager.add_tool('XY', XYPlotButton)
            xy = fig.canvas.manager.toolmanager.get_tool('XY')
            fig.canvas.manager.toolbar.add_tool(xy, "toolgroup")
    # adjust the margins
    fig.subplots_adjust(wspace=0.0, hspace=0.05, left=0.1, right=0.95, top=0.95, bottom=0.1)
    # change the window title
    fig.canvas.manager.set_window_title(site_name)
    # loop over the groups to be plotted
    for i, lg in enumerate(d.keys()):
        for j, group in enumerate(d[lg].keys()):
            # get a dictionary to hold the variables to be plotted
            var = {}
            # loop over the variables to be plotted in each group
            for k, label in enumerate(d[lg][group]):
                # put the variable into the dictionary
                var[k] = pfp_utils.GetVariable(ds, label, group=group)
                # get the start and end datetimes
                sdt = var[k]["DateTime"][0]
                edt = var[k]["DateTime"][-1]
                # plot the variable on the axis for this group
                axs[i].plot(var[k]["DateTime"], var[k]["Data"], label=label,
                            marker=".", color=colors[numpy.mod(j+k, 8)])
                # only label the Y axis on the first variable
                if j+k == 0:
                    axs[i].set_ylabel("(" + var[k]["Attr"]["units"] + ")")
            # add the legend
            axs[i].legend()
            # set the X axis limits to the start and end datetimes
            axs[i].set_xlim([sdt, edt])
            # only add the title to the first axes
            if i == 0:
                title_str = site_name + ": " + sdt.strftime("%Y-%m-%d") + " to "
                title_str += edt.strftime("%Y-%m-%d")
                axs[i].set_title(title_str)
            # only label the X axis of the last axes
            if i == nrows-1:
                axs[i].set_xlabel("Date")
    # if only 2 variables with the same variable name prefix were selected ...
    if nrows == 1 and len(all_labels) == 2:
        cid = fig.canvas.mpl_connect('button_press_event', lambda x: petsg_onclick(x, fig))
        # call the XY scatter plot routine when the X axis limits change
        axs[0].callbacks.connect("xlim_changed", lambda x: xy_xlims_changed(x, fig, var))
    # render the plot
    plt.draw()
    plt.ioff()
    return
def petsg_onclick(event, fig):
    """
    Purpose:
      Get the cursor shape when a button is clicked.  This will be used in
      xy_lims_changed() to decide whether or not to draw an XY plot of the
      2 variables lotted in the time series.
      An XY plot will only be drawn if the cursor shape is a set of
      crosshairs (shape==2) indicating that the zoom tool is enabled.
    """
    # save the cursor shape as an attribute of the current figure
    fig.cursor_shape_on_click = fig.canvas.cursor().shape()
    return
def xy_xlims_changed(event_ax, fig, var):
    """
    Purpose:
     Plot data for the date range selected in a zoom operation and add a robust
     linear regression line plus equation to the plot.
    Date: December 2022
    Author: PRI
    """
    # only do this if the figure cursor is a crosshair, the cursor shape used for
    # the zoom tool, this prevents a scatter plot being triggered by pressing the
    # "Home", "Back" or "Forward" buttons (cursor is an arrow) or by using the pan
    # tool (cursor is a closed fist)
    if fig.cursor_shape_on_click != 2:
        return
    # reset the cursor shape to prevent triggering an XY plot when Home, Forward or
    # Backward is pressed
    fig.cursor_shape_on_click = 0
    # get the XY button on the figure toolbar
    xy = fig.canvas.manager.toolmanager.get_tool('XY')
    # check to see if the XY button is toggled on ...
    if not xy.toggled:
        # if not, then don't produce an XY plot
        return
    # get the date when the mouse button was pressed at the start of the zoom
    press_date = mdt.num2date(event_ax.get_xlim()[0]).replace(tzinfo=None)
    # get the date when the mouse button was released at the end of the zoom
    release_date = mdt.num2date(event_ax.get_xlim()[1]).replace(tzinfo=None)
    # make sure the start date is the earliest of the 2
    start = min([press_date, release_date])
    # and the end date is the latest of the 2
    end = max([press_date, release_date])
    # get the indices of the datetimes nearest to the start and end
    si = pfp_utils.find_nearest_value(var[0]["DateTime"], start)
    ei = pfp_utils.find_nearest_value(var[0]["DateTime"], end)
    plot_start = var[0]["DateTime"][si]
    plot_end = var[0]["DateTime"][ei-1]
    title = plot_start.strftime("%Y-%m-%d %H:%M") + " to " + plot_end.strftime("%Y-%m-%d %H:%M")
    plt.ion()
    fig_xy, ax_xy = plt.subplots(nrows=1, ncols=1)
    fig_xy.suptitle(title)
    ax_xy.plot(var[0]["Data"][si:ei], var[1]["Data"][si:ei], 'b.')
    ax_xy.set_xlabel(var[0]["Label"]+" ("+var[0]["Attr"]["units"]+")")
    ax_xy.set_ylabel(var[1]["Label"]+" ("+var[1]["Attr"]["units"]+")")
    mask = numpy.ma.mask_or(numpy.ma.getmaskarray(var[0]["Data"][si:ei]),
                            numpy.ma.getmaskarray(var[1]["Data"][si:ei]))
    x_nm = numpy.ma.compressed(numpy.ma.array(var[0]["Data"][si:ei], mask=mask, copy=True))
    if len(x_nm) == 0:
        return
    x_nm = sm.add_constant(x_nm,prepend=False)
    y_nm = numpy.ma.compressed(numpy.ma.array(var[1]["Data"][si:ei], mask=mask, copy=True))
    if len(y_nm) == 0:
        return
    resrlm = sm.RLM(y_nm,x_nm,M=sm.robust.norms.TukeyBiweight()).fit()
    if numpy.isnan(resrlm.params[0]):
        resrlm = sm.RLM(y_nm,x_nm,M=sm.robust.norms.TrimmedMean()).fit()
    r = numpy.corrcoef(numpy.ma.compressed(numpy.ma.array(var[0]["Data"][si:ei], mask=mask, copy=True)),
                       numpy.ma.compressed(numpy.ma.array(var[1]["Data"][si:ei], mask=mask, copy=True)))
    eqnstr = 'y = %.3fx + %.3f (RLM)'%(resrlm.params[0],resrlm.params[1])
    ax_xy.plot(x_nm[:,0],resrlm.fittedvalues,'r--',linewidth=3)
    ax_xy.text(0.5,0.93,eqnstr,fontsize=8,horizontalalignment='center',transform=ax_xy.transAxes)
    eqnstr = 'r = %.3f'%(r[0][1])
    ax_xy.text(0.5,0.89,eqnstr,fontsize=8,horizontalalignment='center',transform=ax_xy.transAxes)
    fig_xy.tight_layout()
    plt.draw()
    plt.ioff()
    return
def plottimeseries(cf, nFig, dsa, dsb):
    SiteName = dsa.root["Attributes"]['site_name']
    Level = dsb.root["Attributes"]['processing_level']
    ts = int(dsa.root["Attributes"]['time_step'])
    ldt = dsa.root["Variables"]["DateTime"]["Data"]
    Month = ldt[0].month
    Hdh = [dt.hour+(dt.minute+dt.second/float(60))/float(60) for dt in ldt]
    p = plot_setup(cf,nFig)
    logger.info(' Plotting series: '+str(p['SeriesList']))
    L1XArray = dsa.root["Variables"]['DateTime']['Data']
    L2XArray = dsb.root["Variables"]['DateTime']['Data']
    p['XAxMin'] = min(L2XArray)
    p['XAxMax'] = max(L2XArray)
    p['loc'],p['fmt'] = get_ticks(p['XAxMin'],p['XAxMax'])
    # turn on interactive plotting
    show_plots = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "show_plots", default="yes")
    if show_plots.lower() == "yes":
        plt.ion()
    else:
        current_backend = plt.get_backend()
        plt.switch_backend("agg")
        plt.ioff()
    # check to see if a figure with the same title already exists
    fig_titles = []
    # get a list of figure titles
    for i in plt.get_fignums():
        # get the figure
        figa = plt.figure(i)
        # get the figure title
        if len(figa.texts) > 0:
            fig_title = figa.texts[0].get_text()
            # strip out the site name
            idx = fig_title.index(":")
            # and append to the figure title list
            fig_titles.append(fig_title[idx+2:])
    # check to see if a figure with the same title already exists
    if p['PlotDescription'] in fig_titles:
        # if it does, get the figure number (figure numbers start from 1)
        fig_num = fig_titles.index(p['PlotDescription']) + 1
        # get the figure
        fig = plt.figure(fig_num)
        # clear the figure (we should only update axes, not the whole figure)
        fig.clf()
    else:
        # create the figure if it doesn't already exist
        fig = plt.figure(figsize=(p['PlotWidth'],p['PlotHeight']))
    fig.canvas.manager.set_window_title(p['PlotDescription'])
    plt.figtext(0.5,0.95,SiteName+': '+p['PlotDescription'],ha='center',size=16)
    for ThisOne, n in zip(p['SeriesList'],list(range(p['nGraphs']))):
        if ThisOne in list(dsa.root["Variables"].keys()):
            p["Units"] = ""
            if "units" in dsa.root["Variables"][ThisOne]["Attr"]:
                p["Units"] = dsa.root["Variables"][ThisOne]["Attr"]["units"]
            p['YAxOrg'] = p['ts_YAxOrg'] + n*p['yaxOrgOffset']
            L1YArray,p['nRecs'],p['nNotM'],p['nMskd'] = get_yarray(dsa, ThisOne)
            # check the control file to see if the Y axis minima have been specified
            nSer = p['SeriesList'].index(ThisOne)
            p['LYAxMax'],p['LYAxMin'] = get_yaxislimitsfromcf(cf,nFig,'YLMax','YLMin',nSer,L1YArray)
            plot_onetimeseries_left(fig,n,ThisOne,L1XArray,L1YArray,p)
        if ThisOne in list(dsb.root["Variables"].keys()):
            bflag = dsb.root["Variables"][ThisOne]['Flag']
            p["Units"] = ""
            if "units" in dsb.root["Variables"][ThisOne]["Attr"]:
                p["Units"] = dsb.root["Variables"][ThisOne]["Attr"]["units"]
            p['YAxOrg'] = p['ts_YAxOrg'] + n*p['yaxOrgOffset']
            #Plot the Level 2 data series on the same X axis but with the scale on the right Y axis.
            L2YArray,p['nRecs'],p['nNotM'],p['nMskd'] = get_yarray(dsb, ThisOne)
            # check the control file to see if the Y axis minima have been specified
            nSer = p['SeriesList'].index(ThisOne)
            p['RYAxMax'],p['RYAxMin'] = get_yaxislimitsfromcf(cf,nFig,'YRMax','YRMin',nSer,L2YArray)
            plot_onetimeseries_right(fig,n,ThisOne,L2XArray,L2YArray,p)

            #Plot the diurnal averages.
            Hr2,Av2,Sd2,Mx2,Mn2=get_diurnalstats(Hdh, dsb.root["Variables"][ThisOne]['Data'], ts)
            Av2 = numpy.ma.masked_where(Av2==c.missing_value,Av2)
            Sd2 = numpy.ma.masked_where(Sd2==c.missing_value,Sd2)
            Mx2 = numpy.ma.masked_where(Mx2==c.missing_value,Mx2)
            Mn2 = numpy.ma.masked_where(Mn2==c.missing_value,Mn2)
            hr2_ax = fig.add_axes([p['hr1_XAxOrg'],p['YAxOrg'],p['hr2_XAxLen'],p['ts_YAxLen']])
            #hr2_ax.hold(True)
            hr2_ax.plot(Hr2,Av2,'y-',Hr2,Mx2,'r-',Hr2,Mn2,'b-')
            section = pfp_utils.get_cfsection(cf, ThisOne, mode='quiet')
            if section != None:
                if 'DiurnalCheck' in list(cf[section][ThisOne].keys()):
                    NSdarr = numpy.array(pfp_ck.parse_rangecheck_limit(cf[section][ThisOne]['DiurnalCheck']['numsd']))
                    nSd = NSdarr[Month-1]
                    hr2_ax.plot(Hr2,Av2+nSd*Sd2,'r.',Hr2,Av2-nSd*Sd2,'b.')
            plt.xlim(0,24)
            plt.xticks([0,6,12,18,24])
            if n==0:
                hr2_ax.set_xlabel('Hour',visible=True)
            else:
                hr2_ax.set_xlabel('',visible=False)
                plt.setp(hr2_ax.get_xticklabels(), visible=False)
            #if n > 0: plt.setp(hr2_ax.get_xticklabels(), visible=False)

            # vertical lines to show frequency distribution of flags
            bins = numpy.arange(0.5,23.5)
            ind = bins[:len(bins)-1]+0.5
            index = numpy.where(numpy.mod(bflag,10)==0)    # find the elements with flag = 0, 10, 20 etc
            bflag[index] = 0                               # set them all to 0
            hist, bin_edges = numpy.histogram(bflag, bins=bins)
            ymin = hist*0
            delta = 0.01*(numpy.max(hist)-numpy.min(hist))
            bar_ax = fig.add_axes([p['hr2_XAxOrg'],p['YAxOrg'],p['bar_XAxLen'],p['ts_YAxLen']])
            bar_ax.set_ylim(0,numpy.max([1,numpy.max(hist)]))
            bar_ax.vlines(ind,ymin,hist)
            for i,j in zip(ind,hist):
                if j>0.05*numpy.max(hist): bar_ax.text(i,j+delta,str(int(i)),ha='center',size='small')
            if n==0:
                bar_ax.set_xlabel('Flag',visible=True)
            else:
                bar_ax.set_xlabel('',visible=False)
                plt.setp(bar_ax.get_xticklabels(), visible=False)
            #if n > 0: plt.setp(bar_ax.get_xticklabels(), visible=False)
        else:
            logger.warning("  Variable " + ThisOne + " not in data structure")
        # get the plot path and save a hard copy of the plot
        plot_path = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="plots/")
        plot_path = os.path.join(plot_path, Level, "")
        if not os.path.exists(plot_path):
            os.makedirs(plot_path)
        fname = os.path.join(plot_path, SiteName.replace(' ','')+'_'+Level+'_'+p['PlotDescription'].replace(' ','')+'.png')
        fig.savefig(fname,format='png')
    # draw the plot on the screen
    if show_plots.lower() == "yes":
        plt.draw()
        pfp_utils.mypause(0.5)
        plt.ioff()
    else:
        plt.close(fig)
        plt.switch_backend(current_backend)
        plt.ion()
    return

def plot_quickcheck_seb(nFig, plot_title, figure_name, data, daily):
    logger.info(" Doing surface energy balance plots")
    Fa_30min = data["Fa"]["Data"]
    Fh_30min = data["Fh"]["Data"]
    Fe_30min = data["Fe"]["Data"]
    mask = numpy.ma.mask_or(Fa_30min.mask, Fe_30min.mask)
    mask = numpy.ma.mask_or(mask, Fh_30min.mask)
    Fa_SEB = numpy.ma.array(Fa_30min, mask=mask, copy=True)
    FhpFe_SEB = (numpy.ma.array(Fh_30min, mask=mask, copy=True) +
                 numpy.ma.array(Fe_30min, mask=mask, copy=True))
    plt.ion()
    fig = plt.figure(nFig, figsize=(8, 8))
    fig.canvas.manager.set_window_title("Surface Energy Balance")
    plt.figtext(0.5, 0.95, plot_title, horizontalalignment='center', size=16)
    xyplot(Fa_SEB, FhpFe_SEB, sub=[2,2,1], regr=1, title="All hours", xlabel='Fa (W/m^2)', ylabel='Fh+Fe (W/m^2)')
    # scatter plot of (Fh+Fe) versus Fa, 24 hour averages
    mask = numpy.ma.mask_or(daily["Fa"]["Data"].mask, daily["Fe"]["Data"].mask)
    mask = numpy.ma.mask_or(mask, daily["Fh"]["Data"].mask)
    Fa_daily = numpy.ma.array(daily["Fa"]["Data"], mask=mask, copy=True)
    Fe_daily = numpy.ma.array(daily["Fe"]["Data"], mask=mask, copy=True)
    Fh_daily = numpy.ma.array(daily["Fh"]["Data"], mask=mask, copy=True)
    Fa_daily_avg = numpy.ma.average(Fa_daily, axis=1)      # get the daily average
    Fe_daily_avg = numpy.ma.average(Fe_daily, axis=1)
    Fh_daily_avg = numpy.ma.average(Fh_daily, axis=1)
    FhpFe_daily_avg = Fh_daily_avg + Fe_daily_avg
    xyplot(Fa_daily_avg, FhpFe_daily_avg, sub=[2,2,2], regr=1, thru0=1,
           title="Daily Average", xlabel="Fa (W/m^2)", ylabel="Fh+Fe (W/m^2)")
    # scatter plot of (Fh+Fe) versus Fa, day time
    day_mask = (data["Fsd"]["Data"] >= 10)
    Fa_day = numpy.ma.masked_where(day_mask == False, Fa_30min)
    Fe_day = numpy.ma.masked_where(day_mask == False, Fe_30min)
    Fh_day = numpy.ma.masked_where(day_mask == False, Fh_30min)
    mask = numpy.ma.mask_or(Fa_day.mask, Fe_day.mask)
    mask = numpy.ma.mask_or(mask, Fh_day.mask)
    Fa_day = numpy.ma.array(Fa_day, mask=mask, copy=True)
    Fe_day = numpy.ma.array(Fe_day, mask=mask, copy=True)
    Fh_day = numpy.ma.array(Fh_day, mask=mask, copy=True)
    FhpFe_day = Fh_day + Fe_day
    xyplot(Fa_day, FhpFe_day, sub=[2,2,3], regr=1, title="Day", xlabel="Fa (W/m^2)", ylabel="Fh+Fe (W/m^2)")
    # scatter plot of (Fh+Fe) versus Fa, night time
    night_mask = (data["Fsd"]["Data"] < 10)
    Fa_night = numpy.ma.masked_where(night_mask==False, Fa_30min)
    Fe_night = numpy.ma.masked_where(night_mask==False, Fe_30min)
    Fh_night = numpy.ma.masked_where(night_mask==False, Fh_30min)
    mask = numpy.ma.mask_or(Fa_night.mask, Fe_night.mask)
    mask = numpy.ma.mask_or(mask, Fh_night.mask)
    Fa_night = numpy.ma.array(Fa_night, mask=mask, copy=True)
    Fe_night = numpy.ma.array(Fe_night, mask=mask, copy=True)
    Fh_night = numpy.ma.array(Fh_night, mask=mask, copy=True)
    FhpFe_night = Fh_night + Fe_night
    xyplot(Fa_night, FhpFe_night, sub=[2,2,4], regr=1, title="Night", xlabel="Fa (W/m^2)", ylabel="Fh+Fe (W/m^2)")
    # hard copy of plot
    fig.savefig(figure_name, format='png')
    # draw the plot on the screen
    plt.draw()
    plt.ioff()

def plot_quickcheck_get_seb(daily):
    # get the SEB ratio
    # get the daytime data, defined by Fsd>10 W/m^2
    nm = daily["night_mask"]["Data"]
    Fa_daily = daily["Fa"]["Data"]
    Fe_daily = daily["Fe"]["Data"]
    Fh_daily = daily["Fh"]["Data"]
    Fa_day = numpy.ma.masked_where(nm == True, Fa_daily)
    Fe_day = numpy.ma.masked_where(nm == True, Fe_daily)
    Fh_day = numpy.ma.masked_where(nm == True, Fh_daily)
    # mask based on dependencies, set all to missing if any missing
    mask = numpy.ma.mask_or(Fa_day.mask, Fe_day.mask)
    mask = numpy.ma.mask_or(mask, Fh_day.mask)
    # apply the mask
    Fa_day = numpy.ma.array(Fa_day, mask=mask, copy=True)
    Fe_day = numpy.ma.array(Fe_day, mask=mask, copy=True)
    Fh_day = numpy.ma.array(Fh_day, mask=mask, copy=True)
    # get the daily averages
    Fa_day_avg = numpy.ma.average(Fa_day, axis=1)
    Fe_day_avg = numpy.ma.average(Fe_day, axis=1)
    Fh_day_avg = numpy.ma.average(Fh_day, axis=1)
    SEB = {"label": "(Fh+Fe)/Fa"}
    # get the number of values in the daily average
    SEB["Count"] = numpy.ma.count(Fh_day, axis=1)
    # get the SEB ratio
    SEB["Avg"] = (Fe_day_avg + Fh_day_avg)/Fa_day_avg
    SEB["Avg"] = numpy.ma.masked_where(SEB["Count"] <= 5, SEB["Avg"])
    idx = numpy.where(numpy.ma.getmaskarray(SEB["Avg"]) == True)[0]
    SEB["Count"][idx] = 0
    return SEB

def plot_quickcheck_get_ef(daily):
    # get the EF
    # get the daytime data, defined by Fsd>10 W/m^2
    nm = daily["night_mask"]["Data"]
    Fa_daily = daily["Fa"]["Data"]
    Fe_daily = daily["Fe"]["Data"]
    Fa_day = numpy.ma.masked_where(nm == True, Fa_daily)
    Fe_day = numpy.ma.masked_where(nm == True, Fe_daily)
    # mask based on dependencies, set all to missing if any missing
    mask = numpy.ma.mask_or(Fa_day.mask, Fe_day.mask)
    # apply the mask
    Fa_day = numpy.ma.array(Fa_day, mask=mask, copy=True)
    Fe_day = numpy.ma.array(Fe_day, mask=mask, copy=True)
    # get the daily averages
    Fa_day_avg = numpy.ma.average(Fa_day, axis=1)
    Fe_day_avg = numpy.ma.average(Fe_day, axis=1)
    # get the number of values in the daily average
    EF = {"label": "EF=Fe/Fa"}
    EF["Count"] = numpy.ma.count(Fe_day, axis=1)
    # get the EF ratio
    EF["Avg"] = Fe_day_avg/Fa_day_avg
    EF["Avg"] = numpy.ma.masked_where(EF["Count"] <= 5, EF["Avg"])
    idx = numpy.where(numpy.ma.getmaskarray(EF["Avg"]) == True)[0]
    EF["Count"][idx] = 0
    return EF

def plot_quickcheck_get_br(daily):
    # get the BR
    # get the daytime data, defined by Fsd>10 W/m^2
    nm = daily["night_mask"]["Data"]
    Fh_daily = daily["Fh"]["Data"]
    Fe_daily = daily["Fe"]["Data"]
    Fe_day = numpy.ma.masked_where(nm == True, Fe_daily)
    Fh_day = numpy.ma.masked_where(nm == True, Fh_daily)
    # mask based on dependencies, set all to missing if any missing
    mask = numpy.ma.mask_or(Fe_day.mask, Fh_day.mask)
    # apply the mask
    Fe_day = numpy.ma.array(Fe_day, mask=mask, copy=True)
    Fh_day = numpy.ma.array(Fh_day, mask=mask, copy=True)
    # get the daily averages
    Fe_day_avg = numpy.ma.average(Fe_day, axis=1)
    Fh_day_avg = numpy.ma.average(Fh_day, axis=1)
    # get the number of values in the daily average
    BR = {"label": "BR=Fh/Fe"}
    BR["Count"] = numpy.ma.count(Fh_day, axis=1)
    # get the BR ratio
    BR["Avg"] = Fh_day_avg/Fe_day_avg
    BR["Avg"] = numpy.ma.masked_where(BR["Count"] <= 5, BR["Avg"])
    idx = numpy.where(numpy.ma.getmaskarray(BR["Avg"]) == True)[0]
    BR["Count"][idx] = 0
    return BR

def plot_quickcheck_get_wue(daily):
    # get the Wue
    # get the daytime data, defined by Fsd>10 W/m^2
    nm = daily["night_mask"]["Data"]
    Fc_daily = daily["Fco2"]["Data"]
    Fe_daily = daily["Fe"]["Data"]
    Fe_day = numpy.ma.masked_where(nm == True, Fe_daily)
    Fc_day = numpy.ma.masked_where(nm == True, Fc_daily)
    # mask based on dependencies, set all to missing if any missing
    mask = numpy.ma.mask_or(Fe_day.mask, Fc_day.mask)
    # apply the mask
    Fe_day = numpy.ma.array(Fe_day,mask=mask, copy=True)
    Fc_day = numpy.ma.array(Fc_day,mask=mask, copy=True)
    # get the daily averages
    Fe_day_avg = numpy.ma.average(Fe_day, axis=1)
    Fc_day_avg = numpy.ma.average(Fc_day, axis=1)
    # get the number of values in the daily average
    WUE = {"label": "WUE=Fc/Fe"}
    WUE["Count"] = numpy.ma.count(Fc_day, axis=1)
    WUE["Avg"] = Fc_day_avg/Fe_day_avg
    WUE["Avg"] = numpy.ma.masked_where(WUE["Count"] <= 5, WUE["Avg"])
    idx = numpy.where(numpy.ma.getmaskarray(WUE["Avg"]) == True)[0]
    WUE["Avg"][idx] = 0
    return WUE

def plot_quickcheck_get_avg(daily, label, filter_type=None):
    """
    Purpose:
     Apply a day time or night time filter to data, if reuested, and return
     the daily average of the (filtered) data and the number of data points
     used to provide the average.
    Usage:
     avg, count = pfp_plot.plot_quickcheck_get_avg(daily, label, filter_type="day")
     where;
      daily is a dictionary of data as 2D arrays (axis 0 is hour of the day, axis 1 is the day)
      label is the label of the data
      filter_type is the type of filter to apply ("day", "night" or None)
     and
      avg is the daily average
      count is the number of points used in the average
    Author: PRI
    Date: March 2019
    """
    if filter_type is None:
        data = daily[label]["Data"]
    elif filter_type.lower() == "day":
        dm = daily["day_mask"]["Data"]
        data = numpy.ma.masked_where(dm == False, daily[label]["Data"])
    elif filter_type.lower() == "night":
        nm = daily["night_mask"]["Data"]
        data = numpy.ma.masked_where(nm == False, daily[label]["Data"])
    else:
        msg = "plot_quickcheck_get_avg: unrecognised filter type (" + filter_type + ")"
        logger.warning(msg)
        msg = "plot_quickcheck_get_avg: no filter applied"
        logger.warning(msg)
    avg = numpy.ma.average(data, axis=1)
    count = numpy.ma.count(data, axis=1)
    return avg, count

def plot_quickcheck(cf):
    nFig = 0
    # get the netCDF filename
    ncfilename = pfp_io.get_infilenamefromcf(cf)
    # read the netCDF file and return the data structure "ds"
    ds = pfp_io.NetCDFRead(ncfilename)
    if ds.info["returncodes"]["value"] != 0: return
    series_list = list(ds.root["Variables"].keys())
    # get the time step
    ts = int(float(ds.root["Attributes"]["time_step"]))
    # get the site name
    site_name = ds.root["Attributes"]["site_name"]
    level = ds.root["Attributes"]["processing_level"]
    # get the datetime series
    DateTime = ds.root["Variables"]["DateTime"]["Data"]
    # get the initial start and end dates
    StartDate = str(DateTime[0])
    EndDate = str(DateTime[-1])
    # find the start index of the first whole day (time=00:30)
    si = pfp_utils.GetDateIndex(DateTime, StartDate, ts=ts, default=0, match="startnextday")
    # find the end index of the last whole day (time=00:00)
    ei = pfp_utils.GetDateIndex(DateTime, EndDate, ts=ts, default=-1, match="endpreviousday")
    DateTime = DateTime[si:ei+1]
    nrecs = len(DateTime)
    plot_title = site_name + ": " + DateTime[0].strftime("%Y-%m-%d") + " to " + DateTime[-1].strftime("%Y-%m-%d")
    # get the final start and end dates
    StartDate = str(DateTime[0])
    EndDate = str(DateTime[-1])
    # get the 30 minute data from the data structure
    logger.info(" Getting data from data structure")
    data = {"Month":{"Attr":{}}, "Hour":{"Attr":{}}, "Minute":{"Attr":{}}}
    # do the month, hour and minute separately
    data["Month"]["Data"] = numpy.array([d.month for d in DateTime])
    data["Hour"]["Data"] = numpy.array([d.hour for d in DateTime])
    data["Minute"]["Data"] = numpy.array([d.minute for d in DateTime])
    # now do the data we want to plot
    data_list = ["Fsd", "Fsu", "Fld", "Flu", "Fn",
                 "Fg", "Fa", "Fe", "Fh", "Fco2", "ustar",
                 "Ta", "H2O", "CO2", "Precip", "Ws",
                 "Sws", "Ts"]
    for label in data_list:
        if label in series_list:
            data[label] = pfp_utils.GetVariable(ds, label, start=si, end=ei)
        else:
            data[label] = pfp_utils.CreateEmptyVariable(label, nrecs, datetime=DateTime)
    # get the number of days in the data set
    ntsInDay = float(24.0*60.0/float(ts))
    if math.modf(ntsInDay)[0] != 0:
        msg = " Time step (" + str(ts) + ") is not a sub-multiple of 60 minutes "
        logger.error(msg)
        return
    ntsInDay = int(ntsInDay)
    nDays = float(len(DateTime))/ntsInDay
    if math.modf(nDays)[0] != 0:
        msg = "Not a whole number of days (" + str(nDays) +")"
        logger.error(msg)
        return
    nDays = int(nDays)
    logger.info(" Getting daily averages from 30 minute data")
    # reshape the 1D array of 30 minute data into a 2D array of (nDays,ntsInDay)
    DT_daily = DateTime[0::ntsInDay]
    daily = {}
    for label in list(data.keys()):
        daily[label] = {"label": label}
        daily[label]["Data"] = data[label]["Data"].reshape(nDays, ntsInDay)
        daily[label]["Attr"] = data[label]["Attr"]
    # add the day and night masks
    daily["day_mask"] = {"Data": (data["Fsd"]["Data"] >= 10).reshape(nDays, ntsInDay)}
    daily["night_mask"] = {"Data": (data["Fsd"]["Data"] < 10).reshape(nDays, ntsInDay)}
    # get the daily ratios
    daily["SEB"] = plot_quickcheck_get_seb(daily)
    daily["EF"] = plot_quickcheck_get_ef(daily)
    daily["BR"] = plot_quickcheck_get_br(daily)
    daily["WUE"] = plot_quickcheck_get_wue(daily)
    daily["Sws"]["Avg"], daily["Sws"]["Count"] = plot_quickcheck_get_avg(daily, "Sws")
    daily["Precip"]["Avg"], daily["Precip"]["Count"] = plot_quickcheck_get_avg(daily, "Precip")
    # scatter plot of (Fh+Fe) versus Fa, all data
    nFig = nFig + 1
    file_name = site_name.replace(" ", "") + "_" + level + "_QC_SEB_30minutes.png"
    figure_name = os.path.join("plots", file_name)
    plot_quickcheck_seb(nFig, plot_title, figure_name, data, daily)
    pfp_utils.mypause(0.5)
    # plot the daily ratios
    cmap = plt.cm.get_cmap("RdYlBu")
    logger.info(" Doing the daily ratios plot")
    plt.ion()
    nFig = nFig + 1
    fig = plt.figure(nFig, figsize=(9, 6))
    fig.canvas.manager.set_window_title("Daily Average Ratios")
    plt.figtext(0.5, 0.95, plot_title, horizontalalignment="center", size=16)
    plt.figtext(0.5, 0.90, "Day time data points only", horizontalalignment="center", size=14)
    tsplot1_list = ["SEB", "EF", "BR", "WUE", "Sws", "Precip"]
    nplots = len(tsplot1_list)
    for nrow, label in enumerate(tsplot1_list):
        percent = 100*daily[label]["Count"]/ntsInDay
        tsplot(DT_daily, daily[label]["Avg"], sub=[nplots, 1, nrow+1], ylabel=label,
               colours=percent, cmap=cmap, vmin=0, vmax=100)
    file_name = site_name.replace(" ", "") + "_" + level + "_QC_DailyRatios.png"
    figure_name = os.path.join("plots", file_name)
    fig.savefig(figure_name, format="png")
    plt.draw()
    pfp_utils.mypause(0.5)
    # plot the daily average radiation
    nFig = nFig + 1
    fig = plt.figure(nFig, figsize=(9, 6))
    fig.canvas.manager.set_window_title("Daily Average Radiation")
    plt.figtext(0.5, 0.95, plot_title, horizontalalignment="center", size=16)
    tsplot2_list = ["Fsd", "Fsu", "Fld", "Flu", "Fn", "Fg"]
    nplots = len(tsplot2_list)
    for nrow, label in enumerate(tsplot2_list):
        daily[label]["Avg"], daily[label]["Count"] = plot_quickcheck_get_avg(daily, label)
        percent = 100*daily[label]["Count"]/ntsInDay
        tsplot(DT_daily, daily[label]["Avg"], sub=[nplots, 1, nrow+1], ylabel=label,
               colours=percent, cmap=cmap, vmin=0, vmax=100)
    file_name = site_name.replace(" ", "") + "_" + level +"_QC_DailyRadn.png"
    figure_name = os.path.join("plots", file_name)
    fig.savefig(figure_name, format="png")
    plt.draw()
    pfp_utils.mypause(0.5)
    # plot the daily average fluxes
    nFig = nFig + 1
    fig = plt.figure(nFig, figsize=(9, 6))
    fig.canvas.manager.set_window_title("Daily Average Fluxes")
    plt.figtext(0.5, 0.95, plot_title, horizontalalignment="center", size=16)
    plt.figtext(0.5, 0.90, "Day time data points only", horizontalalignment="center", size=14)
    tsplot3_list = ["Fsd", "Fa", "Fe", "Fh", "Fco2"]
    nplots = len(tsplot3_list)
    for nrow, label in enumerate(tsplot3_list):
        daily[label]["Avg"], daily[label]["Count"] = plot_quickcheck_get_avg(daily, label, filter_type="day")
        percent = 100*daily[label]["Count"]/ntsInDay
        tsplot(DT_daily, daily[label]["Avg"], sub=[nplots, 1, nrow+1], ylabel=label,
               colours=percent, cmap=cmap, vmin=0, vmax=100)
    file_name = site_name.replace(" ", "") + "_" + level + "_QC_DailyFluxes.png"
    figure_name = os.path.join("plots", file_name)
    fig.savefig(figure_name, format="png")
    plt.draw()
    pfp_utils.mypause(0.5)
    # plot the daily average meteorology
    nFig = nFig + 1
    fig = plt.figure(nFig, figsize=(9, 6))
    fig.canvas.manager.set_window_title("Daily Average Meteorology")
    plt.figtext(0.5, 0.95, plot_title, horizontalalignment="center", size=16)
    tsplot4_list = ["Ta", "H2O", "CO2", "Ws", "Precip"]
    nplots = len(tsplot4_list)
    for nrow, label in enumerate(tsplot4_list):
        daily[label]["Avg"], daily[label]["Count"] = plot_quickcheck_get_avg(daily, label)
        percent = 100*daily[label]["Count"]/ntsInDay
        tsplot(DT_daily, daily[label]["Avg"], sub=[nplots, 1, nrow+1], ylabel=label,
               colours=percent, cmap=cmap, vmin=0, vmax=100)
    file_name = site_name.replace(" ", "") + "_" + level + "_QC_DailyMet.png"
    figure_name = os.path.join("plots", file_name)
    fig.savefig(figure_name, format="png")
    plt.draw()
    pfp_utils.mypause(0.5)
    # plot the daily average soil data
    nFig = nFig + 1
    fig = plt.figure(nFig, figsize=(9, 6))
    fig.canvas.manager.set_window_title("Daily Average Soil Data")
    plt.figtext(0.5, 0.95, plot_title, horizontalalignment="center", size=16)
    tsplot5_list = ["Ta", "Ts", "Sws", "Fg", "Precip"]
    nplots = len(tsplot5_list)
    for nrow, label in enumerate(tsplot5_list):
        daily[label]["Avg"], daily[label]["Count"] = plot_quickcheck_get_avg(daily, label)
        percent = 100*daily[label]["Count"]/ntsInDay
        tsplot(DT_daily, daily[label]["Avg"], sub=[nplots, 1, nrow+1], ylabel=label,
               colours=percent, cmap=cmap, vmin=0, vmax=100)
    file_name = site_name.replace(" ", "") + "_" + level + "_QC_DailySoil.png"
    figure_name = os.path.join("plots", file_name)
    fig.savefig(figure_name, format="png")
    plt.draw()
    pfp_utils.mypause(0.5)
    # *** end of section for time series of daily averages
    # *** start of section for diurnal plots by month ***
    # month labels
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    # variable labels
    labels = ["Fsd", "Fsu", "Fa", "Fn", "Fg", "Ta", "Ts", "Fh", "Fe", "Fco2"]
    # get the colour map, points will be coloured according to the percentage of good data
    cm = plt.cm.get_cmap("RdYlBu")
    # 12 plots per page, 1 for each month
    nrows = 4
    ncols = 3
    # loop over the variables to be plotted
    for label in labels:
        # skip if the label is not in the data structure
        if label not in series_list:
            continue
        # put up a log message
        msg = " Doing the monthly diurnal plots for " + label
        logger.info(msg)
        # increment the figure number so we don't overwrite any plots
        nFig = nFig + 1
        # create the sub plots, 4 rows of 3 columns each with shared X and Y axes
        fig, axs = plt.subplots(num=nFig, nrows=nrows, ncols=ncols, sharex=True, sharey=True,
                                    figsize=(8, 10))
        # do the window and plot titles
        window_title = "Diurnal " + label
        fig.canvas.manager.set_window_title(window_title)
        plt.figtext(0.5, 0.95, plot_title, horizontalalignment="center", size=16)
        # loop over each month
        for j, i in enumerate([12] + list(range(1, 12))):
            # indices of this month in the daily data
            idx = numpy.where(daily["Month"]["Data"] == i)[0]
            # column and row number for this plot
            ncol = numpy.mod(j, ncols)
            nrow = j//ncols
            # skip month and remove axes if there is no data for this month
            if len(idx) == 0:
                axs[nrow, ncol].remove()
                continue
            # turn off the X axis and tick labels for all but the last row
            if nrow > 0:
                axs[nrow-1, ncol].tick_params(labelbottom=False)
                axs[nrow-1, ncol].xaxis.label.set_visible(False)
            # turn off the Y axis labels for all but the first column
            if ncol > 0:
                axs[nrow, ncol].yaxis.label.set_visible(False)
            # get the decimal hour
            hr = daily["Hour"]["Data"][idx] + daily["Minute"]["Data"][idx]/float(60)
            # get the average and number of good data points at each time of the day for this month
            avg = numpy.ma.average(daily[label]["Data"][idx], axis=0)
            num = 100*numpy.ma.count(daily[label]["Data"][idx], axis=0)/len(idx)
            # plot the average for each time of the day, colour set by percentage of good data
            ax = axs[nrow, ncol].scatter(hr[0], avg, c=num, cmap=cm, vmin=0, vmax=100)
            # add the title, axis labels, tick marks etc
            axs[nrow, ncol].set_title(months[i-1])
            axs[nrow, ncol].set_xlim([0, 24])
            axs[nrow, ncol].set_xticks([0, 6, 12, 18, 24])
            axs[nrow, ncol].tick_params(labelbottom=True)
            axs[nrow, ncol].set_xlabel("Hour")
            axs[nrow, ncol].set_ylabel(label + " (" + daily[label]["Attr"]["units"] + ")")
            # add colour bar as an inset
            cbins = inset_axes(axs[nrow, ncol], width="50%", height="5%", loc="upper center")
            ticks = [0, 50, 100]
            fig.colorbar(ax, cax=cbins, orientation="horizontal", ticks=ticks)
        # save the plot to file
        level = ds.root["Attributes"]["processing_level"]
        file_name = site_name.replace(" ", "") + "_" + level + "_QC_Diurnal" + label + "ByMonth.png"
        figure_name = os.path.join("plots", file_name)
        fig.savefig(figure_name, format="png")
        # draw the plot on the screen
        plt.draw()
        pfp_utils.mypause(0.5)
    plt.ioff()
    return

def plot_stacked_timeseries(cfg, ds, start=0, end=-1):
    show_plots = pfp_utils.get_optionskeyaslogical(cfg, "show_plots", default=True)
    plot_labels = pfp_utils.get_keyvaluefromcf(cfg, ["Options", "plot_stacked_timeseries"],
                                               "plot_labels", default="")
    site_name = ds.root["Attributes"]["site_name"]
    level = ds.root["Attributes"]["processing_level"]
    ds_labels = sorted(list(ds.root["Variables"].keys()))
    for label in list(plot_labels):
        if label not in ds_labels:
            plot_labels.remove(label)
    if len(plot_labels) < 1:
        msg = "No plot variables in data set"
        logger.error(msg)
        return
    nrows = len(plot_labels)
    if show_plots:
        plt.ion()
    else:
        current_backend = plt.get_backend()
        plt.switch_backend("agg")
        plt.ioff()
    fig, axs = plt.subplots(nrows=nrows, sharex=True, figsize=(7.5, 10.9))
    fig.subplots_adjust(wspace=0.0, hspace=0.05, left=0.11, right=0.95, top=0.95, bottom=0.05)
    for n, label in enumerate(plot_labels):
        var = pfp_utils.GetVariable(ds, label, start=start, end=end)
        percent = str(int(0.5+100*numpy.ma.count(var["Data"])/len(var["Data"]))) + "%"
        sdt = var["DateTime"][0]
        edt = var["DateTime"][-1]
        axs[n].plot(var["DateTime"], var["Data"], "b.")
        axs[n].set_xlim([sdt, edt])
        if n == 0:
            title_str = site_name + ": " + sdt.strftime("%Y-%m-%d") + " to "
            title_str += edt.strftime("%Y-%m-%d")
            axs[n].set_title(title_str)
        if n == nrows-1:
            axs[n].xaxis.set_major_formatter(mdt.DateFormatter('%m-%d'))
            axs[n].set_xlabel("Date")
        axs[n].text(-0.11, 0.6, label, transform=axs[n].transAxes)
        axs[n].text(-0.11, 0.3, percent, transform=axs[n].transAxes)
    plot_path = pfp_utils.get_keyvaluefromcf(cfg, ["Files"], "plot_path", default="./plots/")
    plot_path = os.path.join(plot_path, "timeseries", "")
    if not os.path.exists(plot_path):
        os.makedirs(plot_path)
    pngname = plot_path + site_name.replace(" ","") + "_" + level
    pngname = pngname + "_stacked_timeseries.png"
    fig.savefig(pngname, format="png")
    if show_plots:
        plt.draw()
        pfp_utils.mypause(0.5)
        plt.ioff()
    else:
        plt.close(fig)
        plt.switch_backend(current_backend)
        plt.ion()
    return

def plot_setup(cf, title):
    p = {}
    plot_path = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="plots")
    p["plot_path"] = os.path.join(plot_path, cf["level"], "")
    p['PlotDescription'] = str(title)
    var_string = cf['Plots'][str(title)]['variables']
    p['SeriesList'] = pfp_utils.string_to_list(var_string)
    p['nGraphs'] = len(p['SeriesList'])
    p['PlotWidth'] = 13
    p['PlotHeight'] = 8
    p['ts_YAxOrg'] = 0.08
    p['ts_XAxOrg'] = 0.06
    p['ts_XAxLen'] = 0.6
    p['hr_XAxLen'] = 0.1
    p['ts_YAxLen'] = (0.85 - (p['nGraphs'] - 1)*0.02)/p['nGraphs']
    if p['nGraphs']==1:
        p['yaxOrgOffset'] = (0.85 - p['ts_YAxLen'])
    else:
        p['yaxOrgOffset'] = (0.85 - p['ts_YAxLen'])/(p['nGraphs'] - 1)
    p['hr1_XAxOrg'] = p['ts_XAxOrg']+p['ts_XAxLen']+0.07
    p['hr1_XAxLen'] = p['hr_XAxLen']
    p['hr2_XAxOrg'] = p['hr1_XAxOrg']+p['hr1_XAxLen']+0.05
    p['hr2_XAxLen'] = p['hr_XAxLen']
    p['bar_XAxOrg'] = p['hr1_XAxOrg']+p['hr1_XAxLen']+0.05+p['hr1_XAxLen']+0.05
    p['bar_XAxLen'] = p['hr_XAxLen']
    p['ts_ax_left'] = [None]*p["nGraphs"]
    p['ts_ax_right'] = [None]*p["nGraphs"]
    return p

def plot_onetimeseries_left(fig,n,ThisOne,xarray,yarray,p):
    """
    Purpose:
     Plots a single time series graph with labelling on the left y axis.
    Usage:
     pfp_plot.plot_onetimeseries_left(fig,n,ThisOne,XArray,YArray,p)
      where fig     is a matplotlib figure instance
            n       is the number of this graph
            ThisOne is the series label
            XArray  is a numpy ndarray or masked array of X data (usually datetime)
            YArray  is a numpy ndarray or masked array of Y data
            p       is a dictionary of plot data (created using pfp_plot.plot_setup)
    Side effects:
     Creates a matplotlib plot of time series, diurnal variation and flag statistics.
    Author: PRI
    Date: Sometime
    """
    # check to see if this is the first graph
    if n == 0:
        # if so, define the X axis
        rect = [p['ts_XAxOrg'],p['YAxOrg'],p['ts_XAxLen'],p['ts_YAxLen']]
        ts_ax_left = fig.add_axes(rect)
    else:
        # if not, then use an existing axis
        rect = [p['ts_XAxOrg'],p['YAxOrg'],p['ts_XAxLen'],p['ts_YAxLen']]
        if p["ts_ax_left"][0] is not None:
            # a left axis was defined for the first graph, use it
            ts_ax_left = fig.add_axes(rect,sharex=p["ts_ax_left"][0])
        else:
            # a right axis was defined for the first graph, use it
            ts_ax_left = fig.add_axes(rect,sharex=p["ts_ax_right"][0])
    # put this axis in the plot setup dictionary
    p["ts_ax_left"][n] = ts_ax_left
    # plot the data on this axis
    ts_ax_left.plot(xarray,yarray,'b-')
    # set the axes limits
    ts_ax_left.set_xlim(p['XAxMin'],p['XAxMax'])
    ts_ax_left.set_ylim(p['LYAxMin'],p['LYAxMax'])
    ts_ax_left.tick_params(axis='y', colors='b')
    # check to see if this is the first graph
    if n == 0:
        # if it is, label the X axis
        ts_ax_left.set_xlabel('Date',visible=True)
    else:
        # if it isnt, hide the X axis labels
        ts_ax_left.set_xlabel('',visible=False)
    # now put a text string on the graph with the series plotted, units, number in series,
    # number not masked (data OK) and number masked (data not OK)
    TextStr = ThisOne+'('+p['Units']+')'+str(p['nRecs'])+' '+str(p['nNotM'])+' '+str(p['nMskd'])
    txtXLoc = p['ts_XAxOrg']+0.01
    txtYLoc = p['YAxOrg']+p['ts_YAxLen']-0.025
    plt.figtext(txtXLoc,txtYLoc,TextStr,color='b',horizontalalignment='left')
    if n > 0: plt.setp(ts_ax_left.get_xticklabels(),visible=False)

def plot_onetimeseries_right(fig,n,ThisOne,xarray,yarray,p):
    if p["ts_ax_left"][n] is not None:
        ts_ax_right = p["ts_ax_left"][n].twinx()
    else:
        rect = [p['ts_XAxOrg'],p['YAxOrg'],p['ts_XAxLen'],p['ts_YAxLen']]
        if p["ts_ax_left"][0] is not None:
            # a left axis was defined for the first graph, use it
            ts_ax_right = fig.add_axes(rect,sharex=p["ts_ax_left"][0])
        else:
            # a right axis was defined for the first graph, use it
            ts_ax_right = fig.add_axes(rect,sharex=p["ts_ax_right"][0])
        #ts_ax_right.hold(False)
        ts_ax_right.yaxis.tick_right()
        TextStr = ThisOne+'('+p['Units']+')'
        txtXLoc = p['ts_XAxOrg']+0.01
        txtYLoc = p['YAxOrg']+p['ts_YAxLen']-0.025
        plt.figtext(txtXLoc,txtYLoc,TextStr,color='b',horizontalalignment='left')
    p["ts_ax_right"][n] = ts_ax_right
    ts_ax_right.plot(xarray,yarray,'r-')
    ts_ax_right.set_xlim(p['XAxMin'],p['XAxMax'])
    ts_ax_right.set_ylim(p['RYAxMin'],p['RYAxMax'])
    ts_ax_right.tick_params(axis='y', colors='r')
    if n==0:
        ts_ax_right.set_xlabel('Date',visible=True)
    else:
        ts_ax_right.set_xlabel('',visible=False)
    TextStr = str(p['nNotM'])+' '+str(p['nMskd'])
    txtXLoc = p['ts_XAxOrg']+p['ts_XAxLen']-0.01
    txtYLoc = p['YAxOrg']+p['ts_YAxLen']-0.025
    plt.figtext(txtXLoc,txtYLoc,TextStr,color='r',horizontalalignment='right')
    if n > 0: plt.setp(ts_ax_right.get_xticklabels(),visible=False)

def plot_windrose(cf):
    """
    Purpose:
    Usage:
    Side effects:
    Author: PRI/CE
    Date: May 2022
    """
    wrinfo = plot_windrose_parse_controlfile(cf)
    # read the netCDF file to a data structure
    ds = pfp_io.NetCDFRead(wrinfo["in_filename"])
    # check the required variables are in the data structure
    if not plot_windrose_check_variables(ds, wrinfo):
        return
    # update the info dictionary
    wrinfo["start"] = ds.root["Attributes"]["time_coverage_start"]
    wrinfo["end"] = ds.root["Attributes"]["time_coverage_end"]
    wrinfo["site_name"] = ds.root["Attributes"]["site_name"]
    # plot all the data
    plot_windrose_all(ds, wrinfo)
    # plot the seasonal windrose
    plot_windrose_seasonal(ds, wrinfo)
    return

def plot_windrose_check_variables(ds, wrinfo):
    """ Check the variables named in the control file exist in the data structure."""
    ok = True
    labels = list(ds.root["Variables"].keys())
    for item in ["Fsd", "Wd", "Ws"]:
        name = wrinfo[item]
        if name not in labels:
            msg = name + "(" + item + ") not found in " + wrinfo["in_filename"]
            logger.error(msg)
            ok = False
    return ok

def plot_windrose_parse_controlfile(cf):
    """
    Purpose:
     Parse the windrose control file and return the required information in a
     dictionary.
    Author: PRI/CE
    Date: May 2022
    """
    wrinfo = {}
    # get the input file name from the control file
    wrinfo["in_filename"] = pfp_io.get_infilenamefromcf(cf)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "number_speed_bins", default="8")
    wrinfo["nbins"] = int(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "speed_bin_width", default="1")
    wrinfo["wbins"] = int(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "number_sectors", default="16")
    wrinfo["nsectors"] = int(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "Fsd_threshold", default="10")
    wrinfo["Fsd_threshold"] = int(opt)
    # get the wind direction and wind speed variable names
    wrinfo["Wd"] = pfp_utils.get_keyvaluefromcf(cf, ["Variables", "Wd"], "name", default="Wd")
    wrinfo["Ws"] = pfp_utils.get_keyvaluefromcf(cf, ["Variables", "Ws"], "name", default="Ws")
    wrinfo["Fsd"] = pfp_utils.get_keyvaluefromcf(cf, ["Variables", "Fsd"], "name", default="Fsd")
    # plot path
    wrinfo["plot_path"] = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="plots/")
    if not os.path.exists(wrinfo["plot_path"]):
        os.makedirs(wrinfo["plot_path"])
    return wrinfo

def plot_windrose_all(ds, wrinfo):
    """
    Purpose:
    Usage:
    Side effects:
    Author: PRI/CE
    Date: May 2022
    """
    nbins = wrinfo["nbins"]
    wbins = wrinfo["wbins"]
    nsectors = wrinfo["nsectors"]
    site_name = ds.root["Attributes"]["site_name"]
    level = ds.root["Attributes"]["processing_level"]
    title = site_name + ": " + wrinfo["start"] + " to " + wrinfo["end"]
    title += "; all data"
    # read the variables
    Ws = pfp_utils.GetVariable(ds, wrinfo["Ws"])
    Wd = pfp_utils.GetVariable(ds, wrinfo["Wd"])
    Fsd = pfp_utils.GetVariable(ds, wrinfo["Fsd"])
    mask = numpy.ma.getmaskarray(Ws["Data"])
    mask = numpy.ma.mask_or(mask, numpy.ma.getmaskarray(Wd["Data"]))
    Ws["All"] = numpy.ma.masked_where(mask == True, Ws["Data"])
    Wd["All"] = numpy.ma.masked_where(mask == True, Wd["Data"])
    Ws["All"] = numpy.ma.compressed(Ws["All"])
    Wd["All"] = numpy.ma.compressed(Wd["All"])
    # prepare day/night data
    mask = numpy.ma.mask_or(mask, numpy.ma.getmaskarray(Fsd["Data"]))
    for item in [Ws, Wd, Fsd]:
        item["DayNight"] = numpy.ma.masked_where(mask == True, item["Data"])
        item["DayNight"] = numpy.ma.compressed(item["DayNight"])
    ones = numpy.ones(len(Fsd["DayNight"]))
    zeros = numpy.zeros(len(Fsd["DayNight"]))
    idx = numpy.where(Fsd["DayNight"] <= wrinfo["Fsd_threshold"], ones, zeros)
    plt.ion()
    fig = plt.figure(figsize=(8, 8))
    fig.canvas.manager.set_window_title("Windrose for "+wrinfo["site_name"]+", all data")
    gs = gridspec.GridSpec(2, 2) # 2 rows, 2 columns
    ax1=fig.add_subplot(gs[0, :], projection="windrose") # First row, first column
    ax2=fig.add_subplot(gs[1, 0], projection="windrose") # Second row, first column
    ax3=fig.add_subplot(gs[1, 1], projection="windrose") # Second row, second column
    ax1.box(Wd["All"], Ws["All"], bins=numpy.arange(0, nbins, wbins), nsector=nsectors)
    ax1.legend(loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.25), fontsize=6)
    ax1.set_title("All")
    ax2.box(Wd["DayNight"][idx==0], Ws["DayNight"][idx==0],
            bins=numpy.arange(0, nbins, wbins),
            nsector=nsectors)
    ax2.set_title("Day")
    ax2.legend(loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.25), fontsize=6)
    ax3.box(Wd["DayNight"][idx==1], Ws["DayNight"][idx==1],
            bins=numpy.arange(0, nbins, wbins),
            nsector=nsectors)
    ax3.set_title("Night")
    ax3.legend(loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.25), fontsize=6)
    fig.suptitle(title)
    fig.tight_layout()
    plt.draw()
    file_name = site_name.replace(" ","") + "_" + level + "_" + "windrose_all" + ".png"
    file_name = os.path.join(wrinfo["plot_path"], file_name)
    fig.savefig(file_name, format="png")
    pfp_utils.mypause(0.5)
    plt.ioff()
    return

def plot_windrose_seasonal(ds, wrinfo):
    """
    Purpose:
     Plot windroses for all day time and all night time data.
    Usage:
    Side effects:
    Author: PRI/CE
    Date: May 2022
    """
    nbins = wrinfo["nbins"]
    nsectors = wrinfo["nsectors"]
    wbins = wrinfo["wbins"]
    site_name = ds.root["Attributes"]["site_name"]
    level = ds.root["Attributes"]["processing_level"]
    title = site_name + ": " + wrinfo["start"] + " to " + wrinfo["end"]
    title += "; Seasonal"
    # read the variables
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    ldt["Month"] = numpy.array([dt.month for dt in ldt["Data"]])
    Ws = pfp_utils.GetVariable(ds, wrinfo["Ws"])
    Wd = pfp_utils.GetVariable(ds, wrinfo["Wd"])
    seasons = {"Summer": [12, 1, 2], "Autumn": [3, 4, 5],
               "Winter": [6, 7, 8], "Spring": [9, 10, 11]}
    axs = {}
    plt.ion()
    fig = plt.figure(figsize=(8, 8))
    fig.canvas.manager.set_window_title("Windrose for "+wrinfo["site_name"]+", seasons")
    for s, season in enumerate(seasons):
        cind = numpy.zeros(len(Ws["Data"]))
        for month in seasons[season]:
            idx = numpy.where(ldt["Month"] == month)[0]
            cind[idx] = 1
        wd = Wd["Data"][cind == 1]
        ws = Ws["Data"][cind == 1]
        mask = numpy.ma.getmaskarray(wd)
        mask = numpy.ma.mask_or(mask, numpy.ma.getmaskarray(ws))
        wd = numpy.ma.masked_where(mask == True, wd)
        wd = numpy.ma.compressed(wd)
        ws = numpy.ma.masked_where(mask == True, ws)
        ws = numpy.ma.compressed(ws)
        axs[season] = fig.add_subplot(2, 2, s+1, projection="windrose")
        axs[season].box(wd, ws,
                        bins=numpy.arange(0, nbins, wbins),
                        nsector=nsectors)
        axs[season].set_title(season)
        axs[season].legend(loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.25), fontsize=6)
    fig.suptitle(title)
    fig.tight_layout()
    plt.draw()
    file_name = site_name.replace(" ","") + "_" + level + "_" + "windrose_seasonal" + ".png"
    file_name = os.path.join(wrinfo["plot_path"], file_name)
    fig.savefig(file_name, format="png")
    pfp_utils.mypause(0.5)
    plt.ioff()
    return

def plotxy(cf, title, plt_cf, dsa, dsb):
    SiteName = dsa.root["Attributes"]['site_name']
    Level = dsb.root["Attributes"]['processing_level']
    PlotDescription = str(title)
    # turn on interactive plotting
    show_plots = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "show_plots", default="yes")
    if show_plots.lower() == "yes":
        plt.ion()
    else:
        current_backend = plt.get_backend()
        plt.switch_backend("agg")
        plt.ioff()
    fig = plt.figure()
    fig.clf()
    fig.canvas.manager.set_window_title(PlotDescription)
    plt.figtext(0.5,0.95,SiteName+': '+PlotDescription,ha='center',size=16)
    if "," in plt_cf['xseries']:
        XSeries = plt_cf['xseries'].split(",")
    else:
        XSeries = [plt_cf['xseries']]
    if "," in plt_cf['yseries']:
        YSeries = plt_cf['yseries'].split(",")
    else:
        YSeries = [plt_cf['yseries']]
    logger.info(' Plotting xy: '+str(XSeries)+' v '+str(YSeries))
    if dsa == dsb:
        for xname,yname in zip(XSeries,YSeries):
            xa = pfp_utils.GetVariable(dsa, xname)
            ya = pfp_utils.GetVariable(dsa, yname)
            xyplot(xa["Data"], ya["Data"], sub=[1,1,1],regr=1, xlabel=xname, ylabel=yname)
    else:
        for xname,yname in zip(XSeries, YSeries):
            xa = pfp_utils.GetVariable(dsa, xname)
            ya = pfp_utils.GetVariable(dsa, yname)
            xb = pfp_utils.GetVariable(dsb, xname)
            yb = pfp_utils.GetVariable(dsb, yname)
            xyplot(xa["Data"], ya["Data"], sub=[1,2,1], xlabel=xname, ylabel=yname)
            xyplot(xb["Data"], yb["Data"], sub=[1,2,2], regr=1, xlabel=xname, ylabel=yname)
    plt.draw()
    pfp_utils.mypause(0.5)
    plot_path = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="plots/")
    if not os.path.exists(plot_path):
        os.makedirs(plot_path)
    fname = os.path.join(plot_path, SiteName.replace(' ','')+'_'+Level+'_'+PlotDescription.replace(' ','')+'.png')
    fig.savefig(fname, format='png')
    # draw the plot on the screen
    if show_plots.lower() == "yes":
        plt.draw()
        pfp_utils.mypause(0.5)
        plt.ioff()
    else:
        plt.close(fig)
        plt.switch_backend(current_backend)
        plt.ion()
    return

def xyplot(x,y,sub=[1,1,1],regr=0,thru0=0,title=None,xlabel=None,ylabel=None,fname=None):
    '''Generic XY scatter plot routine'''
    wspace = 0.0
    hspace = 0.0
    plt.subplot(sub[0], sub[1], sub[2])
    plt.plot(x, y, 'b.')
    ax = plt.gca()
    if xlabel is not None:
        plt.xlabel(xlabel)
        hspace = 0.3
    if ylabel is not None:
        plt.ylabel(ylabel)
        wspace = 0.3
    if title is not None:
        plt.title(title)
        hspace = 0.3
    plt.subplots_adjust(wspace=wspace, hspace=hspace)
    if (numpy.ma.count(x) == 0) or (numpy.ma.count(y) == 0):
        return
    if regr==1:
        coefs = numpy.ma.polyfit(numpy.ma.copy(x),numpy.ma.copy(y),1)
        xfit = numpy.ma.array([numpy.ma.min(x),numpy.ma.max(x)], copy=True)
        yfit = numpy.polyval(coefs,xfit)
        r = numpy.ma.corrcoef(x,y)
        eqnstr = 'y = %.3fx + %.3f (OLS)'%(coefs[0],coefs[1])
        plt.plot(xfit,yfit,'r--',linewidth=3)
        plt.text(0.5,0.93,eqnstr,fontsize=8,horizontalalignment='center',transform=ax.transAxes)
        eqnstr = 'r = %.3f'%(r[0][1])
        plt.text(0.5,0.89,eqnstr,fontsize=8,horizontalalignment='center',transform=ax.transAxes)
    elif regr==2:
        mask = (x.mask)|(y.mask)
        x.mask = mask
        y.mask = mask
        x_nm = numpy.ma.compressed(x)
        x_nm = sm.add_constant(x_nm,prepend=False)
        y_nm = numpy.ma.compressed(y)
        if len(y_nm)!=0 or len(x_nm)!=0:
            resrlm = sm.RLM(y_nm,x_nm,M=sm.robust.norms.TukeyBiweight()).fit()
            if numpy.isnan(resrlm.params[0]):
                resrlm = sm.RLM(y_nm,x_nm,M=sm.robust.norms.TrimmedMean()).fit()
            r = numpy.corrcoef(numpy.ma.compressed(x),numpy.ma.compressed(y))
            eqnstr = 'y = %.3fx + %.3f (RLM)'%(resrlm.params[0],resrlm.params[1])
            plt.plot(x_nm[:,0],resrlm.fittedvalues,'r--',linewidth=3)
            plt.text(0.5,0.93,eqnstr,fontsize=8,horizontalalignment='center',transform=ax.transAxes)
            eqnstr = 'r = %.3f'%(r[0][1])
            plt.text(0.5,0.89,eqnstr,fontsize=8,horizontalalignment='center',transform=ax.transAxes)
        else:
            logger.info("xyplot: nothing to plot!")
    if thru0!=0:
        x = x[:,numpy.newaxis]
        a, _, _, _ = numpy.linalg.lstsq(x, y, rcond=-1)
        eqnstr = 'y = %.3fx'%(a)
        plt.text(0.5,0.875,eqnstr,fontsize=8,horizontalalignment='center',transform=ax.transAxes)
    return

def hrplot(x, y, sub=[1,1,1], title=None, xlabel=None, ylabel=None, colours=None, cmap=None,
           show_xtick_labels=True):
    plt.subplot(sub[0],sub[1],sub[2])
    if (y.all() is numpy.ma.masked):
        y = numpy.ma.zeros(len(y))
    if colours is not None:
        #cm = plt.cm.get_cmap("RdYlBu")
        #sc = plt.scatter(x,y,c=colours,cmap=cm)
        #plt.colorbar(sc)
        if cmap is not None:
            plt.scatter(x, y, c=colours, cmap=cmap)
        else:
            plt.scatter(x, y, c=colours)
    else:
        plt.scatter(x,y)
    plt.xlim(0,24)
    plt.xticks([0,6,12,18,24])
    if title is not None:
        plt.title(title)
    if ylabel is not None:
        plt.ylabel(ylabel)
    if xlabel is not None:
        plt.xlabel(xlabel)
    if not show_xtick_labels:
        ax = plt.gca()
        ax.tick_params(labelbottom=False)
    return

def tsplot(x, y, sub=[1,1,1], title=None, xlabel=None, ylabel=None, lineat=None,
           colours=None, cmap=None, vmin=None, vmax=None):
    """
    Purpose:
     Plot a time series of data with optional colouring of points and a colour bar.
    Author: PRI
    Date: Back in the day
    """
    axs = plt.subplot(sub[0],sub[1],sub[2])
    if (y.all() is numpy.ma.masked):
        y = numpy.ma.zeros(len(y))
    if ((colours is not None) and (cmap is not None) and
        (vmin is not None) and (vmax is not None)):
        ax = axs.scatter(x, y, c=colours, cmap=cmap, vmin=vmin, vmax=vmax)
        cbins = inset_axes(axs, width="10%", height="10%", loc="upper right")
        ticks = [0, 50, 100]
        plt.colorbar(ax, cax=cbins, orientation="horizontal", ticks=ticks)
    else:
        ax = axs.scatter(x, y)
    if lineat is not None:
        ax = axs.plot((x[0], x[-1]), (float(lineat), float(lineat)))
    axs.set_xlim([x[0], x[-1]])
    if title is not None:
        plt.title(title)
    if ylabel is not None:
        axs.yaxis.set_label_text(ylabel)
    if xlabel is not None:
        axs.xaxis.set_label_text(xlabel)
    if sub[2] != sub[0]:
        axs.set_xlabel('',visible=False)
        axs.tick_params(labelbottom=False)
    return
