#standard modules
import copy
import logging
from multiprocessing import Pool
import os
#3rd party modules
import dateutil
import numpy
#PFP modules
from scripts import pfp_ck
from scripts import pfp_gfSOLO
from scripts import pfp_io
from scripts import pfp_rp
from scripts import pfp_ts
from scripts import pfp_utils

logger = logging.getLogger("pfp_log")

class Bunch:
    """
    Constructor class for dummy object with attributes defined by keywords
    when instantiated.
    """
    def __init__(self, **kwds):
        self.__dict__.update(kwds)

def EstimateRandomUncertainty(ds, info):
    """
    Purpose:
     Estimate the random uncertainty using the ONEFlux Methods 1 and 2.
    Usage:
    Side effects:
    Author: PRI
    Date: December 2023
    """
    estimate_random_uncertainty_method1(ds, info)
    estimate_random_uncertainty_method2(ds, info)
    return

def estimate_random_uncertainty_method1(ds, info):
    """
    Purpose:
     Estimate the random uncertainty using the ONEFlux Method 1.
     This function is based on random_method_1 in nee_proc/src/randunc.c.
    Usage:
    Side effects:
     We switch from masked arrays to ndarrays with missing data set to
     numpy.nan because the numpy MaskedArray module is slow.
    Author: PRI
    Date: December 2023
    """
    # get number of records, time step etc
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    ts = int(ds.root["Attributes"]["time_step"])
    if ts == 30:
        hour_range = 5
    elif ts == 60:
        hour_range = 3
    else:
        msg = " Time step must be 30 or 60 minnutes (" + str(ts) + ")"
        logger.error(msg)
        raise RuntimeError(msg)
    nperday = int(24*60/ts)
    # get required information
    ierc = info["EstimateRandomUncertainty"]
    labels = ierc["labels"]
    ierc1 = ierc["Method1"]
    # get the Fsd, Ta and VPD tolerances
    Fsd_tol0 = float(ierc1["Fsd"]["tolerance"][0])
    Fsd_tol1 = float(ierc1["Fsd"]["tolerance"][1])
    Fsd_tolerance_min = min([Fsd_tol0, Fsd_tol1])
    Fsd_tolerance_max = max([Fsd_tol0, Fsd_tol1])
    Ta_tolerance = float(ierc1["Ta"]["tolerance"])
    VPD_tolerance = float(ierc1["VPD"]["tolerance"])
    # get the window size
    #window_size = int(ierc1["window_size"])
    window_size = 7
    widx = window_size * nperday + 1
    hour_range = int(ierc1["hour_range"])
    # get the data
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    Fsd = pfp_utils.GetVariable(ds, "Fsd")
    Ta = pfp_utils.GetVariable(ds, "Ta")
    VPD = pfp_utils.GetVariable(ds, "VPD")
    # switch to ndarray with missing data set to numpy.nan
    fsd = numpy.ma.filled(Fsd["Data"], fill_value=numpy.nan)
    ta = numpy.ma.filled(Ta["Data"], fill_value=numpy.nan)
    vpd = numpy.ma.filled(VPD["Data"], fill_value=numpy.nan)
    # construct a list of indices to cover the hour range and window size
    i5t = numpy.tile(numpy.arange(hour_range), window_size*2+1)
    oo = numpy.repeat(numpy.arange(-1*widx, widx, nperday), hour_range)
    idx0 = oo + i5t
    # do the work
    for label in labels:
        # get the variable
        var = pfp_utils.GetVariable(ds, label)
        data = numpy.ma.filled(var["Data"], fill_value=numpy.nan)
        runc_label = label + "_runc"
        runc_value = pfp_utils.CreateEmptyVariable(runc_label, nrecs, datetime=ldt["Data"],
                                                   out_type="ndarray")
        runc_method = pfp_utils.CreateEmptyVariable(runc_label+"_method", nrecs,
                                                    datetime=ldt["Data"], out_type="ndarray")
        runc_number = pfp_utils.CreateEmptyVariable(runc_label+"_number", nrecs,
                                                    datetime=ldt["Data"], out_type="ndarray")
        for j in list(range(nrecs)):
            # if Fsd < Fsd_tolerance_min then Fsd_tolerance = Fsd_tolerance_min
            # if Fsd_tolerance_min <= Fsd <= Fsd_tolerance_max then Fsd_tolerance = Fsd
            # if Fsd > Fsd_tolerance_max then Fsd_tolerance = Fsd_tolerance_max
            Fsd_tolerance = min([Fsd_tolerance_max, max([Fsd_tolerance_min, fsd[j]])])
            idx1 = idx0 + j
            idx1 = idx1[(idx1 >= 0) & (idx1 < nrecs)]
            idx2 = numpy.where((abs(fsd[idx1] - fsd[j]) < Fsd_tolerance) &
                               (abs(ta[idx1] - ta[j]) < Ta_tolerance) &
                               (abs(vpd[idx1] - vpd[j]) < VPD_tolerance) &
                               (~numpy.isnan(data[idx1])))[0]
            #if j == 0:
                #print("oi va vey")
            if len(idx2) >= 5:
                runc_value["Data"][j] = numpy.std(data[idx1[idx2]])
                runc_value["Flag"][j] = int(710)
                runc_method["Data"][j] = int(1)
                runc_method["Flag"][j] = int(0)
                runc_number["Data"][j] = len(idx2)
                runc_number["Flag"][j] = int(0)
            else:
                runc_value["Data"][j] = numpy.nan
                runc_value["Flag"][j] = int(701)
        pfp_utils.CreateVariable(ds, runc_value)
        pfp_utils.CreateVariable(ds, runc_method)
        pfp_utils.CreateVariable(ds, runc_number)
    return

def estimate_random_uncertainty_method2(ds, info):
    """
    Purpose:
     Estimate the random uncertainty using the ONEFlux Method 2.
     This function is based on random_method_2 in nee_proc/src/randunc.c.
    Usage:
    Side effects:
    Author: PRI
    Date: December 2023
    """
    # get number of records, time step etc
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    ts = int(ds.root["Attributes"]["time_step"])
    nperhour = int(60/ts)
    nperday = int(24*nperhour)
    # get number of records, time step etc
    ierc = info["EstimateRandomUncertainty"]
    labels = ierc["labels"]
    ierc2 = ierc["Method2"]
    window_size = ierc2["window_size"]
    half_window_days = max([1, int((window_size/2)+0.5)])
    half_window_indices = int(nperday*half_window_days)
    for label in labels:
        tolerance = float(ierc2[label]["tolerance"])
        limit = float(ierc2[label]["limit"])
        var = pfp_utils.GetVariable(ds, label, out_type="nan")
        var_data = var["Data"]
        runc_label = label + "_runc"
        runc_value = pfp_utils.GetVariable(ds, runc_label, out_type="nan")
        runc_data = runc_value["Data"]
        runc_method = pfp_utils.GetVariable(ds, runc_label+"_method", out_type="nan")
        runc_number = pfp_utils.GetVariable(ds, runc_label+"_number", out_type="nan")
        idx_nan = numpy.where(numpy.isnan(runc_value["Data"]))[0]
        for j in idx_nan:
            if numpy.isnan(var_data[j]):
                continue
            value = abs(var_data[j]*tolerance)
            if value < limit:
                value = limit
            range_min = var_data[j] - value
            range_max = var_data[j] + value
            window_first_index = max([0, j - half_window_indices])
            window_last_index = min([j + half_window_indices, nrecs-1])
            idx1 = numpy.arange(window_first_index, window_last_index+1, 1)
            idx2 = numpy.where(~numpy.isnan(runc_data[idx1]) &
                               ~numpy.isnan(var_data[idx1]) &
                               (var_data[idx1] >= range_min) &
                               (var_data[idx1] <= range_max))[0]
            if len(idx2) >= 1:
                runc_value["Data"][j] = numpy.median(runc_value["Data"][idx1[idx2]])
                runc_value["Flag"][j] = int(720)
                runc_method["Data"][j] = int(2)
                runc_method["Flag"][j] = int(0)
                runc_number["Data"][j] = len(idx2)
                runc_number["Flag"][j] = int(0)
        pfp_utils.CreateVariable(ds, runc_value)
        pfp_utils.CreateVariable(ds, runc_method)
        pfp_utils.CreateVariable(ds, runc_number)
    return
def l7_uncertainty_construct_args(ds7, l7_info, ustar_results):
    cfg = l7_info["cfg"]
    er_labels = ["ER_SOLO", "ER_LT", "ER_LL"]
    fco2_labels = ["Fco2_runc", "Fco2_runc_method", "Fco2_runc_number"]
    nee_labels = ["NEE_SOLO", "NEE_LT", "NEE_LL"]
    nep_labels = ["NEP_SOLO", "NEP_LT", "NEP_LL"]
    gpp_labels = ["GPP_SOLO", "GPP_LT", "GPP_LL"]
    subset_labels = er_labels + nee_labels + nep_labels + gpp_labels + fco2_labels
    percentiles = [0.02275, 0.15865, 0.25, 0.5, 0.75, 0.84135, 0.97725]
    args = []
    for n, percentile in enumerate(percentiles):
        d = {}
        d["percentile"] = percentile
        d["l7_info"] = copy.deepcopy(l7_info)
        d["ustar_results"] = copy.deepcopy(ustar_results)
        d["ds7"] = copy.deepcopy(ds7)
        d["main_gui"] = Bunch(stop_flag=False, cfg=cfg, mode="batch")
        d["subset_labels"] = copy.deepcopy(subset_labels)
        args.append(d)
    return args
def l7_uncertainty_run(args):
    if args[0]["l7_info"]["Options"]["multiprocessing"]:
        # spread the load across available CPUs
        number_cpus = min([os.cpu_count()-1, len(args)])
        msg = " Starting uncertainty estimation with " + str(number_cpus) + " cores"
        logger.info(msg)
        msg = "  This may take several minutes, read another paper ...."
        logger.info(msg)
        logger.setLevel(logging.WARNING)
        #with Pool(number_cpus) as pool:
            #dsp = pool.map(l7_uncertainty_worker, args)
        pool = Pool(number_cpus)
        dsp = pool.map(l7_uncertainty_worker, args)
        pool.close()
        pool.join()
        logger.setLevel(logging.INFO)
        msg = " Finished uncertainty estimation"
        logger.info(msg)
    else:
        dsp = []
        msg = " Starting uncertainty estimation on 1 core"
        logger.info(msg)
        msg = "  This may take several minutes, read another paper ...."
        logger.info(msg)
        logger.setLevel(logging.WARNING)
        for n, arg in enumerate(args):
            dsw = l7_uncertainty_worker(arg)
            dsp.append(dsw)
        logger.setLevel(logging.INFO)
        msg = " Finished uncertainty estimation"
        logger.info(msg)
    return dsp
def l7_uncertainty_worker(item):
    percentile = item["percentile"]
    #print("Starting "+str(percentile))
    l7_info = item["l7_info"]
    ustar_results = item["ustar_results"]
    ds7 = item["ds7"]
    main_gui = item["main_gui"]
    subset_labels = item["subset_labels"]
    #msg = " Processing percentile " + str(percentile)
    #logger.info(msg)
    l7_info["ERUsingLloydTaylor"]["info"]["sheet_suffix"] = str(percentile)
    l7_info["ERUsingLasslop"]["info"]["sheet_suffix"] = str(percentile)
    ustar_thresholds = pfp_rp.GetUstarThresholdPercentiles(ustar_results, percentile)
    #print(str(percentile)+" finished pfp_rp.GetUstarThresholdPercentiles")
    pfp_ck.ApplyTurbulenceFilter(ds7, l7_info, ustar_threshold=ustar_thresholds)
    #print(str(percentile)+" finished pfp_ck.ApplyTurbulenceFilter")
    EstimateRandomUncertainty(ds7, l7_info)
    #print(str(percentile)+" finished EstimateRandomUncertainty")
    #pfp_gf.GapFillUsingInterpolation(ds7, l7_info)
    l7_info["GapFillUsingSOLO"]["info"]["percentile"] = str(percentile)
    pfp_gfSOLO.GapFillUsingSOLO(main_gui, ds7, l7_info, "GapFillUsingSOLO")
    #print(str(percentile)+" finished pfp_gfSOLO.GapFillUsingSOLO")
    pfp_ts.MergeSeriesUsingDict(ds7, l7_info, merge_order="standard")
    #print(str(percentile)+" finished pfp_ts.MergeSeriesUsingDict")
    pfp_rp.GetERFromFco2(ds7, l7_info)
    #print(str(percentile)+" finished pfp_rp.GetERFromFco2")
    pfp_rp.ERUsingSOLO(main_gui, ds7, l7_info, "ERUsingSOLO")
    #print(str(percentile)+" finished pfp_rp.ERUsingSOLO")
    pfp_rp.ERUsingLloydTaylor(ds7, l7_info)
    #print(str(percentile)+" finished pfp_rp.ERUsingLloydTaylor")
    pfp_rp.ERUsingLasslop(ds7, l7_info)
    #print(str(percentile)+" finished pfp_rp.ERUsingLasslop")
    pfp_ts.MergeSeriesUsingDict(ds7, l7_info, merge_order="standard")
    #print(str(percentile)+" finished pfp_ts.MergeSeriesUsingDict")
    pfp_rp.CalculateNEE(ds7, l7_info)
    #print(str(percentile)+" finished pfp_rp.CalculateNEE")
    pfp_rp.CalculateNEP(ds7, l7_info)
    #print(str(percentile)+" finished pfp_rp.CalculateNEP")
    pfp_rp.PartitionNEE(ds7, l7_info)
    #print(str(percentile)+" finished pfp_rp.Partition")
    subset_attr = {"nc_nrecs": ds7.root["Attributes"]["nc_nrecs"],
                   "time_step": ds7.root["Attributes"]["time_step"],
                   "percentile": str(percentile)}
    for year in list(ustar_thresholds.keys()):
        key = "ustar_threshold_" + str(year)
        value = ustar_thresholds[year]["ustar_mean"]
        subset_attr[key] = str(value)
    dss = pfp_io.SubsetDataStructure(ds7, subset_labels, subset_attr=subset_attr)
    #print("Finished "+str(percentile))
    #msg = " Finished percentile " + str(percentile)
    #logger.info(msg)
    return dss
