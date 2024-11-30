# standard modules
import copy
import logging
import os
# 3rd party modules
import pandas
# PFP modules
from scripts import pfp_ck
from scripts import pfp_gf
from scripts import pfp_gfALT
from scripts import pfp_gfMDS
from scripts import pfp_gfSOLO
from scripts import pfp_io
from scripts import pfp_parse
from scripts import pfp_rp
from scripts import pfp_ts
from scripts import pfp_uncertainty
from scripts import pfp_utils

logger = logging.getLogger("pfp_log")

def l1_read_input(cfg):
    """
    Purpose:
     Reads input files, either an Excel workbook or a collection of CSV files,
     and returns the data as a data structure.
    Usage:
    Side effects:
     Returns a data structure containing the data specified in the L1
     control file.
    Author: PRI
    Date: February 2020
    """
    # parse the L1 control file
    l1_info = pfp_parse.ParseL1ControlFile(cfg)
    # read the input file into a pandas data frame
    dfs = pfp_io.ReadInputFile(l1_info)
    # check the timestamps
    pfp_io.CheckTimeStamps(dfs, l1_info, fix=True)
    # merge the data frames (1 per Excel worksheet)
    df = pfp_io.MergeDataFrames(dfs, l1_info)
    # convert the data frame to a PFP data structure and add metadata
    ds = pfp_io.DataFrameToDataStructure(df, l1_info)
    # write the processing level to a global attribute
    ds.root["Attributes"]["processing_level"] = "L1"
    # apply linear corrections to the data
    pfp_ck.do_linear(cfg, ds)
    # create new variables using user defined functions
    pfp_ts.DoFunctions(ds, l1_info["read_excel"])
    # apply offset to wind directions
    pfp_ck.do_wd_offset(cfg, ds)
    # calculate variances from standard deviations and vice versa
    pfp_ts.CalculateStandardDeviations(ds)
    # check missing data and QC flags are consistent
    pfp_utils.CheckQCFlags(ds)
    return ds

def l2_quality_control(cf,ds1):
    """
        Perform initial QA/QC on flux data
        Generates L2 from L1 data
        * check parameters specified in control file

        Functions performed:
            pfp_ck.do_rangecheck*
            pfp_ck.do_CSATcheck
            pfp_ck.do_7500check
            pfp_ck.do_diurnalcheck*
            pfp_ck.do_excludedates*
            pfp_ck.do_excludehours*
            pfp_ts.albedo
        """
    # make a copy of the L1 data
    ds2 = copy.deepcopy(ds1)
    # set some attributes for this level
    pfp_utils.UpdateGlobalAttributes(cf, ds2, "L2")
    # apply linear corrections to the data
    pfp_ck.do_linear(cf, ds2)
    # apply the quality control checks (range, diurnal, exclude dates and exclude hours
    pfp_ck.do_qcchecks(cf, ds2)
    # do the CSAT diagnostic check
    pfp_ck.do_SONICcheck(cf, ds2)
    # do the IRGA diagnostic check
    pfp_ck.do_IRGAcheck(cf, ds2)
    # check missing data and QC flags are consistent
    pfp_utils.CheckQCFlags(ds2)
    # write series statistics to file
    pfp_io.get_seriesstats(cf, ds2)
    # write the percentage of good data as a variable attribute
    pfp_utils.get_coverage_individual(ds2)
    return ds2

def l3_post_processing(cf, ds2):
    """
    """
    # make a copy of the L2 data
    ds3 = copy.deepcopy(ds2)
    # set some attributes for this level
    pfp_utils.UpdateGlobalAttributes(cf, ds3, "L3")
    # parse the control file for information on how the user wants to do the gap filling
    l3_info = pfp_parse.ParseL3ControlFile(cf, ds3)
    combine_series = list(l3_info["CombineSeries"].keys())
    # check to see if we have any imports
    pfp_gf.ImportSeries(ds3, l3_info)
    # ************************
    # *** Merge humidities ***
    # ************************
    # merge whatever humidities are available
    pfp_ts.MergeHumidities(cf, ds3, convert_units=True)
    # **************************
    # *** Merge temperatures ***
    # **************************
    # get the air temperature from the CSAT virtual temperature
    pfp_ts.TaFromTv(cf, ds3)
    # merge the HMP and corrected CSAT data
    if "Ta" in combine_series:
        pfp_ts.CombineSeries(cf, ds3, l3_info["CombineSeries"]["Ta"], convert_units=True)
    pfp_utils.CheckUnits(ds3, "Ta", "degC", convert_units=True)
    # ***************************
    # *** Calcuate humidities ***
    # ***************************
    # calculate humidities (absolute, specific and relative) from whatever is available
    pfp_ts.CalculateHumidities(ds3)
    # ********************************
    # *** Merge CO2 concentrations ***
    # ********************************
    # merge the CO2 concentration
    if "CO2" in combine_series:
        pfp_ts.CombineSeries(cf, ds3, l3_info["CombineSeries"]["CO2"], convert_units=True)
    # ******************************************
    # *** Calculate meteorological variables ***
    # ******************************************
    # Update meteorological variables
    pfp_ts.CalculateMeteorologicalVariables(ds3, l3_info)
    # *************************************************
    # *** Calculate fluxes from covariances section ***
    # *************************************************
    # check to see if the user wants to use the fluxes in the L2 file
    if pfp_utils.get_optionskeyaslogical(cf, "CalculateFluxes", default=True):
        # check the covariance units and change if necessary
        pfp_ts.CheckCovarianceUnits(ds3)
        # do the 2D coordinate rotation
        pfp_ts.CoordRotation2D(cf, ds3, l3_info)
        # do the Massman frequency attenuation correction
        pfp_ts.MassmanStandard(cf, ds3)
        # calculate the fluxes
        pfp_ts.CalculateFluxes(cf, ds3)
        # approximate wT from virtual wT using wA (ref: Campbell OPECSystem manual)
        pfp_ts.FhvtoFh(cf, ds3)
        # correct the H2O & CO2 flux due to effects of flux on density measurements
        if pfp_ts.Fe_WPL(cf, ds3):
            return ds3
        if pfp_ts.Fco2_WPL(cf, ds3):
            return ds3
    # **************************
    # *** CO2 and Fc section ***
    # **************************
    # convert CO2 units if required
    pfp_utils.ConvertCO2Units(cf, ds3)
    # calculate Fco2 storage term - single height only at present
    pfp_ts.CalculateSco2SinglePoint(ds3)
    # convert Fco2 and Sco2 units if required
    pfp_utils.ConvertFco2Units(cf, ds3)
    # merge Fco2 and Sco2 series as required
    for label in ["Fco2", "Sco2"]:
        if label in combine_series:
            pfp_ts.CombineSeries(cf, ds3, l3_info["CombineSeries"][label])
    # correct Fco2 for storage term - only recommended if storage calculated from profile available
    pfp_ts.CorrectFco2ForStorage(cf, ds3)
    # *************************
    # *** Radiation section ***
    # *************************
    # merge the radiation components
    for label in ["Fsd", "Fsu", "Fld", "Flu"]:
        if label in combine_series:
            pfp_ts.CombineSeries(cf, ds3, l3_info["CombineSeries"][label])
    # calculate the net radiation from the Kipp and Zonen CNR1
    pfp_ts.CalculateNetRadiation(cf, ds3)
    if "Fn" in combine_series:
        pfp_ts.CombineSeries(cf, ds3, l3_info["CombineSeries"]["Fn"])
    # ****************************************
    # *** Wind speed and direction section ***
    # ****************************************
    # combine wind speed from the Wind Sentry and the SONIC
    for label in ["Ws", "Wd"]:
        if label in combine_series:
            pfp_ts.CombineSeries(cf, ds3, l3_info["CombineSeries"][label])
    # ********************
    # *** Soil section ***
    # ********************
    # correct soil heat flux for storage
    #    ... either average the raw ground heat flux, soil temperature and moisture
    #        and then do the correction (OzFlux "standard")
    for label in ["Ts", "Sws"]:
        if label in combine_series:
            pfp_ts.CombineSeries(cf, ds3, l3_info["CombineSeries"][label])
    if pfp_utils.get_optionskeyaslogical(cf, "CorrectIndividualFg"):
        #    ... or correct the individual ground heat flux measurements (James' method)
        pfp_ts.CorrectIndividualFgForStorage(cf, ds3)
        if "Fg" in combine_series:
            pfp_ts.CombineSeries(cf, ds3, l3_info["CombineSeries"]["Fg"])
    else:
        if "Fg" in combine_series:
            pfp_ts.CombineSeries(cf, ds3, l3_info["CombineSeries"]["Fg"])
        pfp_ts.CorrectFgForStorage(cf, ds3, l3_info)
    # calculate the available energy
    pfp_ts.CalculateAvailableEnergy(ds3)
    # create additional variables using MergeSeries or AverageSeries
    if "extras" in l3_info["CombineSeries"]:
        pfp_ts.CombineSeries(cf, ds3, l3_info["CombineSeries"]["extras"])
    # calculate ET from Fe
    pfp_ts.CalculateET(ds3, l3_info)
    # Calculate Monin-Obukhov length
    pfp_ts.CalculateMoninObukhovLength(ds3)
    # apply linear corrections to the data
    pfp_ck.do_linear(cf, ds3)
    # re-apply the quality control checks (range, diurnal and rules)
    pfp_ck.do_qcchecks(cf, ds3)
    # check missing data and QC flags are consistent
    pfp_utils.CheckQCFlags(ds3)
    # get the statistics for the QC flags and write these to an Excel spreadsheet
    pfp_io.get_seriesstats(cf, ds3)
    # write the percentage of good data as a variable attribute
    pfp_utils.get_coverage_individual(ds3)
    # write the percentage of good data for groups
    pfp_utils.get_coverage_groups(ds3)
    # remove intermediate series from the data structure
    pfp_ts.RemoveIntermediateSeries(ds3, l3_info)
    return ds3

def l4_gapfill_drivers(main_gui, cf, ds3):
    ds4 = pfp_io.copy_datastructure(cf, ds3)
    # ds4 will be empty (logical false) if an error occurs in copy_datastructure
    # return from this routine if this is the case
    if not ds4:
        return ds4
    # set some attributes for this level
    pfp_utils.UpdateGlobalAttributes(cf, ds4, "L4")
    # parse the control file for information on how the user wants to do the gap filling
    l4_info = pfp_parse.ParseL4ControlFile(cf, ds4)
    # check to see if we have any imports
    pfp_gf.ImportSeries(ds4, l4_info)
    # now do the meteorological driver gap filling
    # *** start of the section that does the gap filling of the drivers ***
    # fill short gaps using interpolation
    pfp_gf.GapFillUsingInterpolation(ds4, l4_info)
    # gap fill using climatology
    if "GapFillFromClimatology" in l4_info:
        pfp_gf.GapFillFromClimatology(ds4, l4_info, "GapFillFromClimatology")
    # do the gap filling using the ACCESS output
    if "GapFillFromAlternate" in l4_info:
        # read the alternate data files
        ds_alt = pfp_gf.ReadAlternateFiles(ds4, l4_info)
        pfp_gfALT.GapFillFromAlternate(main_gui, ds4, ds_alt, l4_info, "GapFillFromAlternate")
        if ds4.info["returncodes"]["value"] != 0:
            return ds4
    # merge the first group of gap filled drivers into a single series
    pfp_ts.MergeSeriesUsingDict(ds4, l4_info, merge_order="prerequisite")
    # re-calculate the net radiation
    pfp_ts.CalculateNetRadiation(cf, ds4)
    # re-calculate the available energy
    pfp_ts.CalculateAvailableEnergy(ds4)
    # merge the second group of gap filled drivers into a single series
    pfp_ts.MergeSeriesUsingDict(ds4, l4_info, merge_order="standard")
    # re-calculate the water vapour concentrations
    pfp_ts.CalculateHumiditiesAfterGapFill(ds4, l4_info)
    # re-calculate the meteorological variables
    pfp_ts.CalculateMeteorologicalVariables(ds4, l4_info)
    # truncate data structure if requested
    pfp_io.TruncateDataStructure(ds4, l4_info)
    # check for any missing data
    pfp_utils.get_missingingapfilledseries(ds4, l4_info)
    # write the percentage of good data as a variable attribute
    pfp_utils.get_coverage_individual(ds4)
    # write the percentage of good data for groups
    pfp_utils.get_coverage_groups(ds4)
    # remove intermediate series from the data structure
    pfp_ts.RemoveIntermediateSeries(ds4, l4_info)
    return ds4

def l5_gapfill_fluxes(main_gui, cf, ds4):
    ds5 = pfp_io.copy_datastructure(cf, ds4)
    # ds5 will be empty (logical false) if an error occurs in copy_datastructure
    # return from this routine if this is the case
    if not ds5:
        return ds5
    # set some attributes for this level
    pfp_utils.UpdateGlobalAttributes(cf, ds5, "L5")
    # parse the control file for information on how the user wants to do the gap filling
    l5_info = pfp_parse.ParseL5ControlFile(cf, ds5)
    # check to see if we have any imports
    pfp_gf.ImportSeries(ds5, l5_info)
    # truncate data structure if requested
    pfp_io.TruncateDataStructure(ds5, l5_info)
    # check for missing data in the drivers
    pfp_gf.CheckDrivers(ds5, l5_info)
    if ds5.info["returncodes"]["value"] != 0:
        return ds5
    # now do the flux gap filling methods
    # *** start of the section that does the gap filling of the fluxes ***
    pfp_gf.CheckGapLengths(cf, ds5, l5_info)
    if ds5.info["returncodes"]["value"] != 0:
        return ds5
    # apply the turbulence filter (if requested)
    #pfp_ck.ApplyTurbulenceFilter(cf, ds5, l5_info)
    #if ds5.info["returncodes"]["value"] != 0:
        #return ds5
    pfp_ck.ApplyTurbulenceFilter(ds5, l5_info)
    # fill short gaps using interpolation
    pfp_gf.GapFillUsingInterpolation(ds5, l5_info)
    # gap fill using marginal distribution sampling
    if "GapFillUsingMDS" in l5_info:
        pfp_gfMDS.GapFillUsingMDS(ds5, l5_info, "GapFillUsingMDS")
    # do the gap filling using SOLO
    if "GapFillUsingSOLO" in l5_info:
        pfp_gfSOLO.GapFillUsingSOLO(main_gui, ds5, l5_info, "GapFillUsingSOLO")
        if ds5.info["returncodes"]["value"] != 0:
            return ds5
    # fill long gaps using SOLO
    do_it = False
    for target in l5_info["CheckTargets"]["targets"]:
        if target in list(l5_info["CheckGapLengths"].keys()):
            if l5_info["CheckGapLengths"][target]["got_long_gaps"]:
                do_it = True
    if "GapFillLongSOLO" in l5_info and do_it:
        pfp_gfSOLO.GapFillUsingSOLO(main_gui, ds5, l5_info, "GapFillLongSOLO")
        if ds5.info["returncodes"]["value"] != 0:
            return ds5
    # merge the gap filled drivers into a single series
    pfp_ts.MergeSeriesUsingDict(ds5, l5_info, merge_order="standard")
    # check that all targets were gap filled
    pfp_gf.CheckTargets(ds5, l5_info)
    if ds5.info["returncodes"]["value"] != 0:
        return ds5
    # calculate Monin-Obukhov length
    pfp_ts.CalculateMoninObukhovLength(ds5)
    # write the percentage of good data as a variable attribute
    pfp_utils.get_coverage_individual(ds5)
    # write the percentage of good data for groups
    pfp_utils.get_coverage_groups(ds5)
    # remove intermediate series from the data structure
    pfp_ts.RemoveIntermediateSeries(ds5, l5_info)
    return ds5

def l6_partition(main_gui, cf, ds5):
    ds6 = pfp_io.copy_datastructure(cf, ds5)
    # ds6 will be empty (logical false) if an error occurs in copy_datastructure
    # return from this routine if this is the case
    if not ds6:
        return ds6
    # set some attributes for this level
    pfp_utils.UpdateGlobalAttributes(cf, ds6, "L6")
    # parse the control file
    l6_info = pfp_parse.ParseL6ControlFile(cf, ds6)
    # check to see if we have any imports
    pfp_gf.ImportSeries(ds6, l6_info)
    # truncate data structure if requested
    pfp_io.TruncateDataStructure(ds6, l6_info)
    # check units of Fco2
    pfp_utils.CheckFco2Units(ds6, "umol/m^2/s", convert_units=True)
    # get ER from the observed Fco2
    pfp_rp.GetERFromFco2(ds6, l6_info)
    # estimate ER using SOLO
    pfp_rp.ERUsingSOLO(main_gui, ds6, l6_info, "ERUsingSOLO")
    # estimate ER using Lloyd-Taylor
    if "ERUsingLloydTaylor" in list(l6_info.keys()):
        try:
            # open the Excel file for writing all outputs
            xl_name = l6_info["ERUsingLloydTaylor"]["info"]["data_file_path"]
            xl_writer = pandas.ExcelWriter(xl_name, engine = "xlsxwriter")
            pfp_rp.ERUsingLloydTaylor(ds6, l6_info, xl_writer)
            xl_writer.close()
        except RuntimeError:
            msg = " Error using Lloyd-Taylor to estimate ER"
            logger.error(msg)
            xl_writer.close()
    else:
        msg = "The Lloyd-Taylor ER method is disabled in the control file"
        logger.warning(msg)
    # estimate ER using Lasslop et al
    if "ERUsingLasslop" in list(l6_info.keys()):
        try:
            # open the Excel file for writing all outputs
            xl_name = l6_info["ERUsingLasslop"]["info"]["data_file_path"]
            xl_writer = pandas.ExcelWriter(xl_name, engine = "xlsxwriter")
            pfp_rp.ERUsingLasslop(ds6, l6_info, xl_writer)
            xl_writer.close()
        except RuntimeError:
            msg = " Error using Lasslop et al to estimate ER"
            logger.error(msg)
            xl_writer.close()
    else:
        msg = "The Lasslop ER method is disabled in the control file"
        logger.warning(msg)
    # merge the estimates of ER with the observations
    pfp_ts.MergeSeriesUsingDict(ds6, l6_info, merge_order="standard")
    # calculate NEE from Fco2 and ER
    pfp_rp.CalculateNEE(ds6, l6_info)
    # calculate NEP from NEE
    pfp_rp.CalculateNEP(ds6, l6_info)
    # calculate ET from Fe
    pfp_ts.CalculateET(ds6, l6_info)
    # partition NEE into GPP and ER
    pfp_rp.PartitionNEE(ds6, l6_info)
    # write the percentage of good data as a variable attribute
    pfp_utils.get_coverage_individual(ds6)
    # write the percentage of good data for groups
    pfp_utils.get_coverage_groups(ds6)
    # remove intermediate series from the data structure
    pfp_ts.RemoveIntermediateSeries(ds6, l6_info)
    # do the L6 summary
    pfp_rp.L6_summary(ds6, l6_info)
    return ds6

def l7_uncertainty(main_gui, cf, ds4, mode="multiprocessing"):
    """
    Purpose:
     Runs L7 to estimate the random, systematic (u* threshold percentiles) and joint
     uncertainties in Fco2, Fe and Fh.
     Follows the methodology used in ONEFlux.
    Useage:
    Side effects:
    Author: PRI
    Date: March 2024
    """
    ds7 = pfp_io.copy_datastructure(cf, ds4)
    # parse the control file
    l7_info = pfp_parse.ParseL7ControlFile(cf, ds7)
    # check to see if we have any imports
    pfp_gf.ImportSeries(ds7, l7_info)
    # truncate data structure if requested
    pfp_io.TruncateDataStructure(ds7, l7_info)
    # get the ustar threshold results
    file_path = l7_info["Files"]["file_path"]
    cpd_filename = l7_info["Files"]["cpd_filename"]
    ustar_results_name = os.path.join(file_path, cpd_filename)
    ustar_results = pfp_rp.get_ustarthreshold_from_results(ustar_results_name)
    # construct the arguments list for the multiprocessing call
    args = pfp_uncertainty.l7_uncertainty_construct_args(ds7, l7_info, ustar_results)
    # run the uncertainty estimation code, multiprocessing or single core
    dsp = pfp_uncertainty.l7_uncertainty_run(args)
    # construct the output data structure
    dso = pfp_io.DataStructure()
    dso.root["Attributes"] = copy.deepcopy(ds7.root["Attributes"])
    for ds in dsp:
        pctl = ds.root["Attributes"]["percentile"]
        setattr(dso, str(pctl), {"Attributes": ds.root["Attributes"],
                                 "Variables": ds.root["Variables"]})
    return dso
