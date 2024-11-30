# standard modules
import copy
import datetime
import os
import logging
# 3rd party modules
import dateutil
import numpy
import xlrd
# PFP modules
from scripts import constants as c
from scripts import pfp_gui
from scripts import pfp_io
from scripts import pfp_ts
from scripts import pfp_utils

logger = logging.getLogger("pfp_log")

def CheckDrivers(ds, l5_info):
    """
    Purpose:
     Check the drvers specified for gap filling for missing data.
    Usage:
    Side effects:
    Author: PRI
    Date: October 2020
    """
    msg = " Checking drivers for missing data"
    logger.info(msg)
    drivers_with_missing = []
    for label in list(l5_info["CheckDrivers"]["drivers"]):
        if label not in ds.root["Variables"].keys():
            msg = "  Requested driver (" + label + ") not found in data structure"
            logger.error(msg)
            ds.info["returncodes"]["message"] = msg
            ds.info["returncodes"]["value"] = 1
            return
        var = pfp_utils.GetVariable(ds, label)
        if numpy.any(numpy.ma.getmaskarray(var["Data"])):
            drivers_with_missing.append(label)
    if len(drivers_with_missing) == 0:
        msg = "  No missing data found in drivers"
        logger.info(msg)
        ds.info["returncodes"] = {"value": 0, "message": msg}
    else:
        dwm = ",".join(drivers_with_missing)
        msg = " Drivers " + dwm + " have missing data, aborting L5 ..."
        logger.error("!!!!!")
        logger.error(msg)
        logger.error("!!!!!")
        ds.info["returncodes"] = {"value": 1, "message": msg}
    return

def CheckGapLengths(cfg, ds, l5_info):
    """
    Purpose:
     Check to see if any of the series being gap filled have long gaps and
     tell the user if they are present.  The user can then opt to continue
     or to add a long-gap filling method (e.g. GapFillLongSOLO) to the
     control file.
    Usage:
    Side effects:
    Author: PRI
    Date: June 2019
    """
    ds.info["returncodes"]["value"] = 0
    l5_info["CheckGapLengths"] = {}
    # get the maximum length for "short" gaps in days
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "MaxShortGapDays", default=30)
    max_short_gap_days = int(opt)
    # maximum length in records
    ts = int(float(ds.root["Attributes"]["time_step"]))
    nperday = 24 * 60//ts
    max_short_gap_records = max_short_gap_days * nperday
    targets_with_long_gaps = []
    # loop over the targets, get the duration and check to see if any exceed the maximum
    targets = l5_info["CheckTargets"]["targets"]
    for target in targets:
        # initialise dictionary entry
        l5_info["CheckGapLengths"][target] = {"got_long_gaps": False,
                                              "got_long_gap_method": False}
        # loop over possible long gap filling methods
        for long_gap_method in ["GapFillLongSOLO"]:
            if long_gap_method in list(cfg["Fluxes"][target].keys()):
                # set logical true if long gap filling method present
                l5_info["CheckGapLengths"][target]["got_long_gap_method"] = True
        # get the data
        variable = pfp_utils.GetVariable(ds, target)
        # get the mask
        mask = numpy.ma.getmaskarray(variable["Data"])
        # get the gaps
        gap_start_end = pfp_utils.contiguous_regions(mask)
        # loop over the gaps
        for start, end in gap_start_end:
            gap_length = end - start
            # check to see if any gaps are longer than the max
            if gap_length > max_short_gap_records:
                # set logical if long gaps present
                l5_info["CheckGapLengths"][target]["got_long_gaps"] = True
                targets_with_long_gaps.append(target)
                break
    # write an info message to the log window
    if len(targets_with_long_gaps) != 0:
        msg = " Series " + ",".join(targets_with_long_gaps) + " have gaps longer than "
        msg = msg + str(max_short_gap_days) + " days"
        logger.warning(msg)
    # check for targets with long gaps but no long gap fill method
    targets_without = []
    for target in targets:
        if (l5_info["CheckGapLengths"][target]["got_long_gaps"] and
            not l5_info["CheckGapLengths"][target]["got_long_gap_method"]):
            targets_without.append(target)
    # if we have any, put up a warning message and let the user decide
    if len(targets_without) != 0:
        if cfg["Options"]["call_mode"].lower() == "interactive":
            # put up a message box, continue or quit
            msg = "The following series have long gaps but no long gap filling method\n"
            msg = msg + "is specified in the control file.\n"
            msg = msg + "    " + ",".join(targets_without) + "\n"
            msg = msg + "To add a long gap fill method, press 'Quit' and edit the control file\n"
            msg = msg + "or press 'Continue' to ignore this warning."
            result = pfp_gui.MsgBox_ContinueOrQuit(msg, title="Warning: Long gaps")
            if result.clickedButton().text() == "Quit":
                # user wants to edit the control file
                msg = " Quitting L5 to edit control file"
                logger.warning(msg)
                ds.info["returncodes"]["message"] = msg
                ds.info["returncodes"]["value"] = 1
            else:
                # user wants to continue, turn on auto-complete for SOLO ...
                if "GapFillUsingSOLO" in l5_info:
                    l5_info["GapFillUsingSOLO"]["gui"]["auto_complete"] = True
                # ... and disable masking of long gaps with MDS
                if "GapFillUsingMDS" in l5_info:
                    l5_info["GapFillUsingMDS"]["info"].pop("MaxShortGapRecords", None)
        else:
            # batch mode, turn on auto-complete for SOLO ...
            if "GapFillUsingSOLO" in l5_info:
                l5_info["GapFillUsingSOLO"]["gui"]["auto_complete"] = True
            # ... and disable masking of long gaps with MDS
            if "GapFillUsingMDS" in l5_info:
                l5_info["GapFillUsingMDS"]["info"].pop("MaxShortGapRecords", None)
    return

def CheckTargets(ds, l5_info):
    """
    Purpose:
     Check the targets specified for gap filling at L5 to see if any of them
     still contain missing data.
    Usage:
    Side effects:
    Author: PRI
    Date: October 2020
    """
    msg = " Checking targets for missing data"
    logger.info(msg)
    # get a list of target variables
    targets = l5_info["CheckTargets"]["targets"]
    series_with_missing_data = []
    for target in targets:
        var = pfp_utils.GetVariable(ds, target)
        if numpy.any(numpy.ma.getmaskarray(var["Data"])):
            series_with_missing_data.append(target)
    if len(series_with_missing_data) == 0:
        msg = "  No missing data found in targets"
        logger.info(msg)
        ds.info["returncodes"] = {"value": 0, "message": msg}
    else:
        s = ",".join(series_with_missing_data)
        msg = " Targets " + s + " contain missing data, aborting L5 ..."
        logger.error("!!!!!")
        logger.error(msg)
        logger.error("!!!!!")
        ds.info["returncodes"] = {"value": 1, "message": msg}
    return

def ReadAlternateFiles(ds, l4_info):
    ds_alt = {}
    l4ao = l4_info["GapFillFromAlternate"]["outputs"]
    # get a list of file names
    files = [l4ao[output]["file_name"] for output in list(l4ao.keys())]
    # read the alternate files
    for f in files:
        # if the file has not already been read, do it now
        if f not in ds_alt:
            ds_alternate = pfp_io.NetCDFRead(f, fixtimestepmethod="round")
            if ds_alternate.info["returncodes"]["value"] != 0: return ds_alt
            ds_alt[f] = gfalternate_matchstartendtimes(ds, ds_alternate)
    return ds_alt

def gfalternate_matchstartendtimes(ds, ds_alternate):
    """
    Purpose:
     Match the start and end times of the alternate and tower data.
     The logic is as follows:
      - if there is no overlap between the alternate and tower data then
        dummy series with missing data are created for the alternate data
        for the period of the tower data
      - if the alternate and tower data overlap then truncate or pad (with
        missing values) the alternate data series so that the periods of the
        tower data and alternate data match.
    Usage:
     gfalternate_matchstartendtimes(ds,ds_alternate)
     where ds is the data structure containing the tower data
           ds_alternate is the data structure containing the alternate data
    Author: PRI
    Date: July 2015
    Modifications:
     June 2022 - rewrote to use pfp_utils.GetVariable() and pfp_utils.CreateVariable()
                 and to return a new data structure instead of modify ds_alternate
                 in place.
    """
    # check the time steps are the same
    ts_tower = int(float(ds.root["Attributes"]["time_step"]))
    ts_alternate = int(float(ds_alternate.root["Attributes"]["time_step"]))
    if ts_tower != ts_alternate:
        msg = " GapFillFromAlternate: time step for tower and alternate data are different, returning ..."
        logger.error(msg)
        ds.info["returncodes"]["GapFillFromAlternate"] = "error"
        return
    # get a list of alternate series
    labels_alternate = [item for item in list(ds_alternate.root["Variables"].keys()) if "_QCFlag" not in item]
    for label in ["DateTime", "DateTime_UTC"]:
        if label in labels_alternate:
            labels_alternate.remove(label)
    # number of records in truncated or padded alternate data
    nRecs_tower = int(ds.root["Attributes"]["nc_nrecs"])
    # create new data strucure to hold alternate data spanning period of tower data
    gattrs = ds_alternate.root["Attributes"]
    ds_matched = pfp_io.DataStructure(global_attributes=gattrs)
    # force the matched datetime to be the tower datetime
    ds_matched.root["Variables"]["DateTime"] = copy.deepcopy(ds.root["Variables"]["DateTime"])
    # update the number of records in the file
    ds_matched.root["Attributes"]["nc_nrecs"] = nRecs_tower
    # get the start and end times of the tower and the alternate data and see if they overlap
    ldt_alternate = ds_alternate.root["Variables"]["DateTime"]["Data"]
    start_alternate = ldt_alternate[0]
    ldt_tower = ds.root["Variables"]["DateTime"]["Data"]
    end_tower = ldt_tower[-1]
    # since the datetime is monotonically increasing we need only check the start datetime
    overlap = start_alternate <= end_tower
    # do the alternate and tower data overlap?
    if overlap:
        # index of alternate datetimes that are also in tower datetimes
        tower_index, alternate_index = pfp_utils.FindMatchingIndices(ldt_tower, ldt_alternate)
        # check that the indices point to the same times
        ldta = [ldt_alternate[i] for i in alternate_index]
        ldtt = [ldt_tower[i] for i in tower_index]
        if ldta != ldtt:
            # and exit with a helpful message if they dont
            msg = " Something went badly wrong at L4 and I'm giving up"
            logger.error(msg)
            raise RuntimeError(msg)
        # loop over the alternate series and truncate or pad as required
        # truncation or padding is handled by the indices
        for label in labels_alternate:
            # get the alternate data
            var_alternate = pfp_utils.GetVariable(ds_alternate, label)
            # create an empty variable of the required length
            attr = copy.deepcopy(var_alternate["Attr"])
            var_overlap = pfp_utils.CreateEmptyVariable(label, nRecs_tower, attr=attr)
            # replace missing data with alternate data where times match
            var_overlap["Data"][tower_index] = var_alternate["Data"][alternate_index]
            var_overlap["Flag"][tower_index] = var_alternate["Flag"][alternate_index]
            # write the truncated or padded series back into the matched data structure
            pfp_utils.CreateVariable(ds_matched, var_overlap)
    else:
        # there is no overlap between the alternate and tower data, create dummy series
        for label in labels_alternate:
            # get the alternate data
            var_alternate = pfp_utils.GetVariable(ds_alternate, label)
            # create an empty variable of the required length
            attr = copy.deepcopy(var_alternate["Attr"])
            var_overlap = pfp_utils.CreateEmptyVariable(label, nRecs_tower, attr=attr)
            # write the truncated or padded series back into the matched data structure
            pfp_utils.CreateVariable(ds_matched, var_overlap)
    ds.info["returncodes"]["GapFillFromAlternate"] = "normal"
    return ds_matched

# functions for GapFillFromClimatology
def GapFillFromClimatology(ds, l4_info, called_by):
    '''
    Gap fill missing data using data from the climatology spreadsheet produced by
    the climatology.py script.
    '''
    if called_by not in list(l4_info.keys()):
        return
    l4co = l4_info[called_by]["outputs"]
    # tell the user what we are going to do
    msg = " Reading climatology file and creating climatology series"
    logger.info(msg)
    # loop over the series to be gap filled using climatology
    cli_xlbooks = {}
    for output in list(l4co.keys()):
        # check to see if there are any gaps in "series"
        #index = numpy.where(abs(ds.root["Variables"][label]['Data']-float(c.missing_value))<c.eps)[0]
        #if len(index)==0: continue                      # no gaps found in "series"
        cli_filename = l4co[output]["file_name"]
        if not os.path.exists(cli_filename):
            logger.error(" GapFillFromClimatology: Climatology file %s doesn't exist", cli_filename)
            continue
        if cli_filename not in cli_xlbooks:
            cli_xlbooks[cli_filename] = xlrd.open_workbook(cli_filename)
        # local pointers to the series name and climatology method
        label = l4co[output]["target"]
        method = l4co[output]["method"]
        flag_code = l4co[output]["flag_code"]
        # do the gap filling
        cli_xlbook = cli_xlbooks[cli_filename]
        # choose the gap filling method
        if method == "interpolated daily":
            gfClimatology_interpolateddaily(ds, label, output, cli_xlbook, flag_code)
        else:
            logger.error(" GapFillFromClimatology: unrecognised method option for %s", label)
            continue

def gfClimatology_interpolateddaily(ds, series, output, xlbook, flag_code):
    """
    Gap fill using data interpolated over a 2D array where the days are
    the rows and the time of day is the columns.
    """
    # description string for this level of processing
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    # gap fill from interpolated 30 minute data
    sheet_name = series + 'i(day)'
    if sheet_name not in xlbook.sheet_names():
        msg = " gfClimatology: sheet " + sheet_name + " not found, skipping ..."
        logger.warning(msg)
        return
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    thissheet = xlbook.sheet_by_name(sheet_name)
    datemode = xlbook.datemode
    basedate = datetime.datetime(1899, 12, 30)
    nts = thissheet.ncols - 1
    ndays = thissheet.nrows - 2
    # read the time stamp values from the climatology worksheet
    tsteps = thissheet.row_values(1, start_colx=1, end_colx=nts+1)
    # read the data from the climatology workbook
    val1d = numpy.ma.zeros(ndays*nts, dtype=numpy.float64)
    # initialise an array for the datetime of the climatological values
    cdt = [None]*nts*ndays
    # loop over the rows (days) of data
    for xlRow in range(ndays):
        # get the Excel datetime value
        xldatenumber = int(thissheet.cell_value(xlRow+2, 0))
        # convert this to a Python Datetime
        xldatetime = basedate + datetime.timedelta(days=xldatenumber + 1462*datemode)
        # fill the climatology datetime array
        cdt[xlRow*nts:(xlRow+1)*nts] = [xldatetime+datetime.timedelta(hours=hh) for hh in tsteps]
        # fill the climatological value array
        val1d[xlRow*nts:(xlRow+1)*nts] = thissheet.row_values(xlRow+2, start_colx=1, end_colx=nts+1)
    # get the data to be filled with climatological values
    var = pfp_utils.GetVariable(ds, series)
    # get an index of missing values
    idx = numpy.where(numpy.ma.getmaskarray(var["Data"]) == True)[0]
    # there must be a better way to do this ...
    # simply using the index (idx) to set a slice of the data array to the gap filled values in val1d
    # does not seem to work (mask stays true on replaced values in data), the work around is to
    # step through the indices, find the time of the missing value in data, find the same time in the
    # gap filled values val1d and set the missing element of data to this element of val1d
    # actually ...
    # this may not be the fastest but it may be the most robust because it matches dates of missing data
    # to dates in the climatology file
    for ii in idx:
        try:
            jj = pfp_utils.find_nearest_value(cdt, ldt[ii])
            var["Data"][ii] = val1d[jj]
            var["Flag"][ii] = numpy.int32(flag_code)
        except ValueError:
            var["Data"][ii] = numpy.float64(c.missing_value)
            var["Flag"][ii] = numpy.int32(flag_code+1)
    # put the gap filled data back into the data structure
    var["Label"] = output
    var["Attr"][descr_level] = "climatology"
    pfp_utils.CreateVariable(ds, var)
    return

def gfClimatology_monthly(ds, series, output, xlbook):
    """ Gap fill using monthly climatology."""
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    Hdh = numpy.array([(d.hour + d.minute/float(60)) for d in ldt["Data"]])
    Month = numpy.array([d.month for d in ldt["Data"]])
    thissheet = xlbook.sheet_by_name(series)
    val1d = numpy.zeros_like(ds.root["Variables"][series]["Data"])
    values = numpy.zeros([48, 12])
    for month in range(1, 13):
        m = (month - 1)
        xlCol = m*5 + 2
        values[:, m] = thissheet.col_values(xlCol)[2:50]
    for i in range(len(ds.root["Variables"][series]["Data"])):
        h = int(2*Hdh[i])
        m = int(Month[i])
        val1d[i] = values[h, m-1]
    index = numpy.where(abs(ds.root["Variables"][output]["Data"] - c.missing_value) < c.eps)[0]
    ds.root["Variables"][output]["Data"][index] = val1d[index]
    ds.root["Variables"][output]["Flag"][index] = numpy.int32(460)

# functions for GapFillUsingInterpolation
def GapFillUsingInterpolation(ds, info):
    """
    Purpose:
     Gap fill variables in the data structure using interpolation.
     All variables in the [Variables], [Drivers] and [Fluxes] section
     are processed.
    Usage:
     pfp_gf.GapFillUsingInterpolation(cf,ds)
     where cf is a control file object
           ds is a data structure
    Author: PRI
    Date: September 2016
    """
    # get the maximum gap length to be filled by interpolation
    max_length_hours = info["GapFillUsingInterpolation"]["MaxGapInterpolate"]
    # bug out if interpolation disabled in control file
    if max_length_hours == 0:
        msg = " Gap fill by interpolation disabled in control file"
        logger.info(msg)
        return
    # get list of variables from control file
    targets = info["GapFillUsingInterpolation"]["targets"]
    # get the interpolation type
    int_type = info["GapFillUsingInterpolation"]["InterpolateType"]
    # tell the user what we are doing
    msg = " Using " + int_type +" interpolation (max. gap = " + str(max_length_hours) +" hours)"
    logger.info(msg)
    # do the business
    pfp_ts.InterpolateOverMissing(ds, targets, max_length_hours=max_length_hours, int_type=int_type)
    return

# miscellaneous L4 routines
def gf_getdiurnalstats(DecHour,Data,ts):
    nInts = 24*int((60/ts)+0.5)
    Num = numpy.ma.zeros(nInts,dtype=int)
    Hr = numpy.ma.zeros(nInts,dtype=float)
    for i in range(nInts):
        Hr[i] = float(i)*ts/60.
    Av = numpy.ma.masked_all(nInts)
    Sd = numpy.ma.masked_all(nInts)
    Mx = numpy.ma.masked_all(nInts)
    Mn = numpy.ma.masked_all(nInts)
    if numpy.size(Data)!=0:
        for i in range(nInts):
            li = numpy.ma.where((abs(DecHour-Hr[i])<c.eps)&(abs(Data-float(c.missing_value))>c.eps))
            Num[i] = numpy.size(li)
            if Num[i]!=0:
                Av[i] = numpy.ma.mean(Data[li])
                Sd[i] = numpy.ma.std(Data[li])
                Mx[i] = numpy.ma.max(Data[li])
                Mn[i] = numpy.ma.min(Data[li])
    return Num, Hr, Av, Sd, Mx, Mn

def ImportSeries(ds, info):
    cfg = info["cfg"]
    # check to see if there is an Imports section
    if "Imports" not in list(cfg.keys()):
        return
    info["ImportSeries"] = {}
    # number of records
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    # get the start and end datetime
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    start_date = ldt[0]
    end_date = ldt[-1]
    # loop over the series in the Imports section
    for label in list(cfg["Imports"].keys()):
        import_filename = pfp_utils.get_keyvaluefromcf(cfg, ["Imports", label],
                                                       "file_name", default="")
        if import_filename == "":
            msg = " ImportSeries: import filename not found in control file, skipping ..."
            logger.warning(msg)
            continue
        var_name = pfp_utils.get_keyvaluefromcf(cfg, ["Imports", label],
                                                "var_name", default="")
        if var_name == "":
            msg = " ImportSeries: variable name not found in control file, skipping ..."
            logger.warning(msg)
            continue
        ds_import = pfp_io.NetCDFRead(import_filename)
        if ds_import.info["returncodes"]["value"] != 0:
            return
        if var_name not in list(ds_import.root["Variables"].keys()):
            msg = " Requested variable not found in imported data"
            logger.warning(msg)
            continue
        msg = "  Importing variable " + label
        logger.info(msg)
        ts_import = int(float(ds_import.root["Attributes"]["time_step"]))
        ldt_import = ds_import.root["Variables"]["DateTime"]["Data"]
        si = pfp_utils.GetDateIndex(ldt_import, start_date, ts=ts_import,
                                    default=0, match="exact")
        ei = pfp_utils.GetDateIndex(ldt_import, end_date, ts=ts_import,
                                    default=len(ldt_import)-1, match="exact")
        var_import = pfp_utils.GetVariable(ds_import, var_name, start=si, end=ei)
        var_import["Attr"]["time_coverage_start"] = ldt_import[0].strftime("%Y-%m-%d %H:%M")
        var_import["Attr"]["time_coverage_end"] = ldt_import[-1].strftime("%Y-%m-%d %H:%M")
        ldt_import = ldt_import[si:ei+1]
        indainb, indbina = pfp_utils.FindMatchingIndices(ldt_import, ldt)
        var = pfp_utils.CreateEmptyVariable(label, nrecs, attr=var_import["Attr"])
        var["Data"][indbina] = var_import["Data"][indainb]
        var["Flag"][indbina] = var_import["Flag"][indainb]
        pfp_utils.CreateVariable(ds, var)
        info["ImportSeries"][label] = {"start": ldt[indbina[0]],
                                       "end": ldt[indbina[-1]]}
    return
