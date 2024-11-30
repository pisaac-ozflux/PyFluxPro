# standard modules
import copy
import dateutil
import logging
import os
# 3rd party modules
# PFP modules
from scripts import pfp_gui
from scripts import pfp_io
from scripts import pfp_utils

logger = logging.getLogger("pfp_log")

def ParseConcatenateControlFile(cf):
    """
    Purpose:
     Make the concatenate information dictionary
    Usage:
    Side effects:
    Author: PRI
    Date: August 2019
    """
    info = {}
    info["cfg"] = copy.deepcopy(cf)
    info["NetCDFConcatenate"] = {"OK": True}
    inc = info["NetCDFConcatenate"]
    # check the control file has a Files section
    if "Files" not in cf:
        msg = " Files section missing from control file"
        logger.error(msg)
        inc["OK"] = False
        return info
    # check the [Files] section contains an [Out] section and an [In] section
    for item in ["Out", "In"]:
        if item not in cf["Files"]:
            msg = " " + item + " subsection missing from Files section"
            logger.error(msg)
            inc["OK"] = False
            return info
    # check the [In] section contains at least 1 entry
    if len(list(cf["Files"]["In"].keys())) < 1:
        msg = " No input files specified"
        logger.error(msg)
        inc["OK"] = False
        return info
    # get a list of the input file names
    inc["in_file_names"] = []
    for key in sorted(list(cf["Files"]["In"].keys())):
        file_name = cf["Files"]["In"][key]
        if os.path.isfile(file_name):
            inc["in_file_names"].append(file_name)
        else:
            msg = " File not found (" + os.path.basename(file_name) + ")"
            logger.warning(msg)
    # check to see if we have any files to concatenate
    if len(inc["in_file_names"]) == 0:
        msg = " No input files to concatenate"
        logger.error(msg)
        inc["OK"] = False
        return info
    # get the output file name
    if "ncFileName" not in cf["Files"]["Out"]:
        msg = " No ncFileName key in Out subsection of Files section"
        logger.error(msg)
        inc["OK"] = False
        return info
    inc["out_file_name"] = cf["Files"]["Out"]["ncFileName"]
    # check the output path exists, create if it doesn't
    file_path, file_name = os.path.split(inc["out_file_name"])
    if not os.path.isdir(file_path):
        os.makedirs(file_path)
    # work through the choices in the [Options] section
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "ApplyMADFilter", default = "")
    inc["ApplyMADFilter"] = str(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "ApplyFco2Storage", default = "No")
    inc["ApplyFco2Storage"] = str(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "NumberOfDimensions", default=3)
    inc["NumberOfDimensions"] = int(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "MaxGapInterpolate", default=0)
    inc["MaxGapInterpolate"] = int(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "FixTimeStepMethod", default="round")
    inc["FixTimeStepMethod"] = str(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "Truncate", default="No")
    inc["Truncate"] = str(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "TruncateThreshold", default=50)
    inc["TruncateThreshold"] = float(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "SeriesToCheck", default="all")
    inc["SeriesToCheck"] = pfp_utils.csv_string_to_list(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "SeriesToKeep", default=None)
    if opt is not None:
        inc["SeriesToKeep"] = pfp_utils.csv_string_to_list(opt)
    # now add the bits and pieces
    inc["time_coverage_start"] = []
    inc["time_coverage_end"] = []
    inc["chrono_files"] = []
    inc["labels"] = []
    inc["attributes"] = ["height", "instrument", "long_name", "standard_name",
                         "statistic_type", "units", "valid_range"]
    # add key for suppressing output of intermediate variables e.g. Cpd etc
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "KeepIntermediateSeries", default="No")
    info["RemoveIntermediateSeries"] = {"KeepIntermediateSeries": opt, "not_output": []}
    return info

def ParseL1ControlFile(cf):
    """
    Purpose:
     Check the contents of the Li control file.
     If the L1 control file contents are OK, return with the required information.
     If the L1 control file contents are not OK, return with an error message.
    """
    logger.info(" Parsing the L1 control file")
    # create the settings dictionary
    l1_info = {"status": {"value": 0, "message": "OK"},
              "read_excel": {}}
    l1ire = l1_info["read_excel"]
    # copy the files section from the control file
    l1ire["Files"] = copy.deepcopy(cf["Files"])
    l1ire["Files"]["file_name"] = os.path.join(cf["Files"]["file_path"], cf["Files"]["in_filename"])
    l1ire["Files"]["in_headerrow"] = cf["Files"]["in_headerrow"]
    l1ire["Files"]["in_firstdatarow"] = cf["Files"]["in_firstdatarow"]
    plot_path = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="./plots/")
    plot_path = os.path.join(plot_path, "L1", "")
    if not os.path.exists(plot_path):
        os.makedirs(plot_path)
    l1ire["Files"]["plot_path"] = plot_path
    # get the global attributes
    l1ire["Global"] = copy.deepcopy(cf["Global"])
    # get the options section
    l1ire["Options"] = copy.deepcopy(cf["Options"])
    # get the variables
    l1ire["Variables"] = copy.deepcopy(cf["Variables"])
    return l1_info

def ParseL3ControlFile(cfg, ds):
    """
    Purpose:
     Parse the L3 control file and return contents in the l3_info dictionary.
    Usage:
    Side effects:
    Author: PRI
    Date: August 2019
    """
    # PRI 7/10/2021 the code to get zms will give unpredictable results if CO2
    #   profile data present
    l3_info = {"status": {"value": 0, "message": "OK"},
               "cfg": {},
               "variables": {"CO2": {}, "Fco2": {}, "Sco2": {}},
               "CombineSeries": {}}
    # copy the control file sections to the l3_info dictionary
    for section in list(cfg.keys()):
        l3_info["cfg"][section] = copy.deepcopy(cfg[section])
    # add key for suppressing output of intermediate variables e.g. Cpd etc
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "KeepIntermediateSeries", default="No")
    l3_info["RemoveIntermediateSeries"] = {"KeepIntermediateSeries": opt, "not_output": []}
    # find out what label is used for CO2
    parse_l3_co2_label(l3_info)
    # get the height of the CO2 measurement
    parse_l3_co2_height(ds, l3_info)
    # get lists of variables to be merged or averaged
    parse_l3_combine(l3_info)
    return l3_info

def parse_l3_combine(info):
    """ Get a list of variables to be merged or averaged at L3. """
    cfg = info["cfg"]
    cfv = cfg["Variables"]
    labels = list(cfv.keys())
    # list of labels that are explicitly referenced in pfp_levels.l3_post_processing()
    l3_labels = ["CO2", "Fco2", "Fg", "Fsd", "Fn", "Sco2", "Sws", "Ta", "Ts", "Wd", "Ws"]
    # cs_labels is a list of all variables using MergeSeries or AverageSeries
    cs_labels = []
    # loop over L3 labels
    for label in l3_labels:
        info["CombineSeries"][label] = [l for l in labels if l.split("_")[0] == label]
        cs_labels = cs_labels + info["CombineSeries"][label]
    cs_labels = list(set(cs_labels))
    # now get a list of any other variables using MergeSeries of AverageSeries that
    # are not in cs_labels
    merge_extras = [l for l in labels if l not in cs_labels and "MergeSeries" in cfv[l]]
    average_extras = [l for l in labels if l not in cs_labels and "AverageSeries" in cfv[l]]
    info["CombineSeries"]["extras"] = merge_extras + average_extras
    return

def parse_l3_co2_label(info):
    """ Get the CO2 variable label."""
    if "CO2" in list(info["cfg"]["Variables"].keys()):
        info["variables"]["CO2"]["label"] = "CO2"
    else:
        msg = " Label for CO2 not found in control file"
        logger.warning(msg)
        info["status"]["value"] = 1
        info["status"]["message"] = msg
    return

def parse_l3_co2_height(ds, info):
    """ Get the height of the CO2 measurement from various sources."""
    cfg = info["cfg"]
    got_zms = False
    labels = list(ds.root["Variables"].keys())
    CO2_label = info["variables"]["CO2"]["label"]
    # try and get the height from the CO2 variable
    if CO2_label in labels:
        # get height from attributes if the CO2 variable is already in the data structure
        try:
            CO2 = pfp_utils.GetVariable(ds, CO2_label)
            zms = float(pfp_utils.strip_non_numeric(CO2["Attr"]["height"]))
            got_zms = True
        except:
            pass
    if not got_zms and "MergeSeries" in list(cfg["Variables"][CO2_label].keys()):
        # get the height from the variables listed in MergeSeries
        try:
            source = cfg["Variables"][CO2_label]["MergeSeries"]["source"]
            source = pfp_utils.convert_csv_string_to_list(source)
            for item in source:
                var = pfp_utils.GetVariable(ds, item)
                zms = float(pfp_utils.strip_non_numeric(var["Attr"]["height"]))
                got_zms = True
                break
        except:
            pass
    if not got_zms and "AverageSeries" in list(cfg["Variables"][CO2_label].keys()):
        # get the height from the variables listed in AverageSeries
        try:
            source = cfg["Variables"][CO2_label]["AverageSeries"]["source"]
            source = pfp_utils.convert_csv_string_to_list(source)
            for item in source:
                var = pfp_utils.GetVariable(ds, item)
                zms = float(pfp_utils.strip_non_numeric(var["Attr"]["height"]))
                got_zms = True
                break
        except:
            pass
    if not got_zms and "tower_height" in list(ds.root["Attributes"].keys()):
        try:
            zms = float(pfp_utils.strip_non_numeric(ds.root["Attributes"]["tower_height"]))
            got_zms = True
        except:
            pass
    if not got_zms and pfp_utils.cfkeycheck(cfg, Base="Options", ThisOne="zms"):
        try:
            zms = float(pfp_utils.strip_non_numeric(cfg["Options"]["zms"]))
            got_zms = True
        except:
            pass
    if got_zms:
        info["variables"]["CO2"]["height"] = zms
    else:
        msg = " Unable to find height for CO2 (" + CO2_label + ") measurement"
        logger.warning(msg)
        info["status"]["value"] = 1
        info["status"]["message"] = msg
    return

def ParseL4ControlFile(cfg, ds):
    """
    Purpose:
     Create the L4 information and setting dictionary.
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
    """
    ds.info["returncodes"]["message"] = "OK"
    ds.info["returncodes"]["value"] = 0
    l4_info = {}
    l4_info["cfg"] = copy.deepcopy(cfg)
    # add key for suppressing output of intermediate variables e.g. Ta_aws
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "KeepIntermediateSeries", default="No")
    l4_info["RemoveIntermediateSeries"] = {"KeepIntermediateSeries": opt, "not_output": []}
    # add key for interpolation
    interpolate_type = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "InterpolateType", default="Akima")
    max_gap_interpolate = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "MaxGapInterpolate", default=3)
    l4_info["GapFillUsingInterpolation"] = {"InterpolateType": str(interpolate_type),
                                            "MaxGapInterpolate": int(max_gap_interpolate)}
    # get a list of keys in the control file
    labels = list(cfg["Drivers"].keys())
    # get a list of targets being gap filled
    targets = sorted(list(cfg["Drivers"].keys()))
    l4_info["GapFillUsingInterpolation"]["targets"] = targets.copy()
    # loop over target variables
    for label in labels:
        if "GapFillFromAlternate" in list(cfg["Drivers"][label].keys()):
            parse_gfalt_createdict(cfg, ds, l4_info, label, "GapFillFromAlternate")
            # check to see if something went wrong
            if ds.info["returncodes"]["value"] != 0:
                # if it has, return to calling routine
                return l4_info
        if "GapFillFromClimatology" in list(cfg["Drivers"][label].keys()):
            parse_gfcli_createdict(cfg, ds, l4_info, label, "GapFillFromClimatology")
            if ds.info["returncodes"]["value"] != 0:
                return l4_info
        if "MergeSeries" in list(cfg["Drivers"][label].keys()):
            parse_gfMergeSeries_createdict(cfg, ds, l4_info, label, "MergeSeries")
    # check to make sure at least 1 output is defined
    outputs = []
    for method in ["GapFillFromAlternate", "GapFillFromClimatology"]:
        if method in list(l4_info.keys()):
            outputs = outputs + list(l4_info[method]["outputs"].keys())
    if len(outputs) == 0:
        msg = " No output variables defined, quitting L4 ..."
        logger.error(msg)
        ds.info["returncodes"]["message"] = msg
        ds.info["returncodes"]["value"] = 1
    return l4_info

def parse_gfcli_createdict(cf, ds, l4_info, label, called_by):
    """
    Purpose:
     Creates a dictionary in l4_info to hold information about the climatological data
     used to gap fill the tower data.
    Usage:
    Side effects:
    Author: PRI
    Date: August 2014
    """
    # make the L4 "description" attrubute for the target variable
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    # flag codes
    flag_codes = {"interpolated daily": 450, "monthly": 460}
    # create the climatology directory in the data structure
    if called_by not in list(l4_info.keys()):
        l4_info[called_by] = {"outputs": {}}
    # name of alternate output series in ds
    outputs = list(cf["Drivers"][label][called_by].keys())
    # loop over the outputs listed in the control file
    l4co = l4_info[called_by]["outputs"]
    cfcli = cf["Drivers"][label][called_by]
    for output in outputs:
        # disable output to netCDF file for this variable
        l4_info["RemoveIntermediateSeries"]["not_output"].append(output)
        # create the dictionary keys for this output
        l4co[output] = {}
        # get the target
        sl = ["Drivers", label, called_by, output]
        l4co[output]["target"] = pfp_utils.get_keyvaluefromcf(cf, sl, "target", default=label)
        # get the source
        l4co[output]["source"] = pfp_utils.get_keyvaluefromcf(cf, sl, "source", default="climatology")
        # Climatology file name
        file_list = list(cf["Files"].keys())
        lower_file_list = [item.lower() for item in file_list]
        # first, look in the [Files] section for a generic file name
        if l4co[output]["source"] in lower_file_list:
            # found a generic file name
            i = lower_file_list.index(l4co[output]["source"].lower())
            l4co[output]["file_name"] = cf["Files"][file_list[i]]
        elif "file_name" in cfcli[output]:
            # no generic file name found, look for a file name in the variable section
            l4co[output]["file_name"] = cfcli[output]["file_name"]
        else:
            # put up some warning messages
            msg = " Unable to resolve climatology source " + l4co[output]["source"] + " for output " + output
            msg = msg + " of variable " + l4co[output]["target"]
            logger.warning(msg)
            msg = " Output " + output + " for variable " + l4co[output]["target"] + " will be skipped!"
            logger.warning(msg)
            # remove the entry in the l4ao dictionary
            l4co.pop(output, None)
            continue
        # climatology variable name if different from name used in control file
        opt = pfp_utils.get_keyvaluefromcf(cfcli, [output], "climatology_name", default=label)
        l4co[output]["climatology_name"] = str(opt)
        # climatology gap filling method
        opt = pfp_utils.get_keyvaluefromcf(cfcli, [output], "method", default="interpolated daily")
        if opt in ["interpolated daily", "monthly"]:
            l4co[output]["method"] = opt
        else:
            l4co[output]["method"] = "interpolated daily"
        # get the flag code
        l4co[output]["flag_code"] = flag_codes[l4co[output]["method"]]
        # create an empty series in ds if the climatology output series doesn't exist yet
        if output not in list(ds.root["Variables"].keys()):
            nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
            var = pfp_utils.CreateEmptyVariable(output, nrecs)
            var["Attr"][descr_level] = "climatology"
            pfp_utils.CreateVariable(ds, var)
    return

def parse_gfalt_createdict(cf, ds, l4_info, label, called_by):
    """
    Purpose:
     Creates a dictionary in l4_info to hold information about the alternate data
     used to gap fill the tower data.
    Usage:
    Side effects:
    Author: PRI
    Date: August 2014
    """
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    # make the L4 "description" attrubute for the target variable
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    # create the alternate data settings directory
    if called_by not in list(l4_info.keys()):
        # create the GapFillFromAlternate dictionary
        l4_info[called_by] = {"outputs": {}, "info": {}, "gui": {}}
        # only need to create the ["info"] dictionary on the first pass
        parse_gfalt_createdict_info(cf, ds, l4_info, called_by)
        if ds.info["returncodes"]["value"] != 0:
            return
        # only need to create the ["gui"] dictionary on the first pass
        parse_gfalt_createdict_gui(cf, ds, l4_info, called_by)
    # get the outputs section
    parse_gfalt_createdict_outputs(cf, l4_info, label, called_by)
    # create an empty series in ds if the alternate output series doesn't exist yet
    outputs = list(l4_info[called_by]["outputs"].keys())
    for output in outputs:
        if output not in list(ds.root["Variables"].keys()):
            l4_info["RemoveIntermediateSeries"]["not_output"].append(output)
            variable = pfp_utils.CreateEmptyVariable(output, nrecs)
            variable["Attr"][descr_level] = l4_info[called_by]["outputs"][output]["source"]
            pfp_utils.CreateVariable(ds, variable)
            variable = pfp_utils.CreateEmptyVariable(label + "_composite", nrecs)
            l4_info["RemoveIntermediateSeries"]["not_output"].append(label + "_composite")
            variable["Attr"][descr_level] = "Composite series of tower and alternate data"
            pfp_utils.CreateVariable(ds, variable)
    return

def parse_gfalt_createdict_info(cf, ds, l4_info, called_by):
    """
    Purpose:
     Create the "info" section of the l4_info[called_by] dictionary.
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
          June 2019 - modified for new l4_info structure
    """
    # reset the return message and code
    ds.info["returncodes"]["message"] = "OK"
    ds.info["returncodes"]["value"] = 0
    # get a local pointer to the tower datetime series
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    plot_path = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="./plots/")
    plot_path = os.path.join(plot_path, "L4", "")
    if not os.path.exists(plot_path):
        try:
            os.makedirs(plot_path)
        except OSError:
            msg = "Unable to create the plot path " + plot_path + "\n"
            msg = msg + "Press 'Quit' to edit the control file.\n"
            msg = msg + "Press 'Continue' to use the default path.\n"
            result = pfp_gui.MsgBox_ContinueOrQuit(msg, title="Warning: L4 plot path")
            if result.clickedButton().text() == "Quit":
                # user wants to edit the control file
                msg = " Quitting L4 to edit control file"
                logger.warning(msg)
                ds.info["returncodes"]["message"] = msg
                ds.info["returncodes"]["value"] = 1
            else:
                plot_path = "./plots/"
                cf["Files"]["plot_path"] = "./plots/"
    # check to see if this is a batch or an interactive run
    call_mode = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "call_mode", default="interactive")
    # create the alternate_info dictionary, this will hold much useful information
    l4a = l4_info[called_by]
    l4a["info"] = {"startdate": ldt[0].strftime("%Y-%m-%d %H:%M"),
                   "enddate": ldt[-1].strftime("%Y-%m-%d %H:%M"),
                   "called_by": called_by,
                   "plot_path": plot_path,
                   "call_mode": call_mode,
                   "time_step": int(float(ds.root["Attributes"]["time_step"])),
                   "site_name": ds.root["Attributes"]["site_name"]}
    out_filename = pfp_io.get_outfilenamefromcf(cf)
    xl_file_name = out_filename.replace('.nc', '_AlternateStats.xls')
    l4a["info"]["xl_file_name"] = xl_file_name
    return

def parse_gfalt_createdict_outputs(cf, l4_info, label, called_by):
    flag_codes = {"default": 400, "aws": 410, "access": 420, "erai": 430, "era5": 440}
    # name of alternate output series in ds
    outputs = list(cf["Drivers"][label][called_by].keys())
    # loop over the outputs listed in the control file
    l4ao = l4_info[called_by]["outputs"]
    cfalt = cf["Drivers"][label][called_by]
    for output in outputs:
        # disable output to netCDF file for this variable
        l4_info["RemoveIntermediateSeries"]["not_output"].append(output)
        # create the dictionary keys for this output
        l4ao[output] = {}
        # get the target
        sl = ["Drivers", label, called_by, output]
        l4ao[output]["target"] = pfp_utils.get_keyvaluefromcf(cf, sl, "target", default=label)
        # source name
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "source", default="")
        l4ao[output]["source"] = opt.lower()
        # output QC flag code
        l4ao[output]["flag_code"] = flag_codes["default"]
        if l4ao[output]["source"] in list(flag_codes.keys()):
            l4ao[output]["flag_code"] = flag_codes[l4ao[output]["source"]]
        # alternate data file name
        # first, look in the [Files] section for a generic file name
        file_list = list(cf["Files"].keys())
        lower_file_list = [item.lower() for item in file_list]
        if l4ao[output]["source"].lower() in lower_file_list:
            # found a generic file name
            i = lower_file_list.index(l4ao[output]["source"].lower())
            l4ao[output]["file_name"] = cf["Files"][file_list[i]]
        elif "file_name" in cfalt[output]:
            # no generic file name found, look for a file name in the variable section
            l4ao[output]["file_name"] = cfalt[output]["file_name"]
        else:
            # put up some warning messages
            msg = " Unable to resolve alternate source " + l4ao[output]["source"] + " for output " + output
            msg = msg + " of variable " + l4ao[output]["target"]
            logger.warning(msg)
            msg = " Output " + output + " for variable " + l4ao[output]["target"] + " will be skipped!"
            logger.warning(msg)
            # remove the entry in the l4ao dictionary
            l4ao.pop(output, None)
            continue
        # get the type of fit
        l4ao[output]["fit_type"] = "OLS"
        if "fit" in cfalt[output]:
            if cfalt[output]["fit"].lower() in ["ols", "ols_thru0", "mrev", "replace", "rma", "odr"]:
                l4ao[output]["fit_type"] = cfalt[output]["fit"]
            else:
                logger.info("gfAlternate: unrecognised fit option for series %s, used OLS", output)
        # correct for lag?
        if "lag" in cfalt[output]:
            if cfalt[output]["lag"].lower() in ["no", "false"]:
                l4ao[output]["lag"] = "no"
            elif cfalt[output]["lag"].lower() in ["yes", "true"]:
                l4ao[output]["lag"] = "yes"
            else:
                logger.info("gfAlternate: unrecognised lag option for series %s", output)
        else:
            l4ao[output]["lag"] = "yes"
        # choose specific alternate variable?
        if "usevars" in cfalt[output]:
            l4ao[output]["usevars"] = pfp_utils.string_to_list(cfalt[output]["usevars"])
        # alternate data variable name if different from name used in control file
        if "alternate_name" in cfalt[output]:
            l4ao[output]["alternate_name"] = cfalt[output]["alternate_name"]
        else:
            l4ao[output]["alternate_name"] = output
        # results of best fit for plotting later on
        l4ao[output]["results"] = {"startdate":[], "enddate":[], "No. points":[], "No. filled":[],
                                   "r":[], "Bias":[], "RMSE":[], "Frac Bias":[], "NMSE":[],
                                   "Avg (Tower)":[], "Avg (Alt)":[],
                                   "Var (Tower)":[], "Var (Alt)":[], "Var ratio":[]}

def parse_gfalt_createdict_gui(cf, ds, l4_info, called_by):
    """
    Purpose:
     Get settings for the GapFillFromAlternate routine from the [GUI]
     section of the L4 control file.
    Usage:
    Side effects:
    Author: PRI
    Date: July 2019
    """
    # local pointer to l4_info["GapFillFromAlternate"]
    l4a = l4_info[called_by]
    # local pointer to datetime
    ldt_tower = pfp_utils.GetVariable(ds, "DateTime")
    # populate the l4_info["gui"] dictionary with things that will be useful
    ts = int(float(ds.root["Attributes"]["time_step"]))
    l4a["gui"]["nperhr"] = int(float(60)/ts + 0.5)
    l4a["gui"]["nperday"] = int(float(24)*l4a["gui"]["nperhr"] + 0.5)
    l4a["gui"]["max_lags"] = int(float(12)*l4a["gui"]["nperhr"] + 0.5)
    # items from the [GUI] section of the control file
    sl = ["GUI", "GapFillFromAlternate"]
    # window length
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "period_option", default="manual")
    if opt == "manual":
        l4a["gui"]["period_option"] = 1
    elif opt == "monthly":
        l4a["gui"]["period_option"] = 2
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "number_months", default=3)
        l4a["gui"]["number_months"] = int(opt)
    elif opt == "days":
        l4a["gui"]["period_option"] = 3
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "number_days", default=90)
        l4a["gui"]["number_days"] = int(opt)
    # overwrite option
    l4a["gui"]["overwrite"] = False
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "overwrite", default="no")
    if opt.lower() == "yes": l4a["gui"]["overwrite"] = True
    # show plots option
    if cf["Options"]["call_mode"].lower() == "interactive":
        l4a["gui"]["show_plots"] = True
    else:
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "show_plots", default="no")
        if opt.lower() == "no":
            l4a["gui"]["show_plots"] = False
    # show all plots option
    l4a["gui"]["show_all"] = False
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "show_all", default="no")
    if opt.lower() == "yes": l4a["gui"]["show_all"] = True
    # auto-complete option
    l4a["gui"]["auto_complete"] = True
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "auto_complete", default="yes")
    if opt.lower() == "no": l4a["gui"]["auto_complete"] = False
    l4a["gui"]["autoforce"] = False
    # minimum percentage of good points required
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "min_percent", default=50)
    l4a["gui"]["min_percent"] = max(int(opt), 1)
    # start date of period to be gap filled
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "start_date", default="YYYY-MM-DD HH:mm")
    try:
        sd = dateutil.parser.parse(opt)
    except (ValueError, TypeError):
        sd = ldt_tower["Data"][0].strftime("%Y-%m-%d %H:%M")
    l4a["gui"]["startdate"] = sd
    # end date of period to be gap filled
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "end_date", default="YYYY-MM-DD HH:mm")
    try:
        ed = dateutil.parser.parse(opt)
    except (ValueError, TypeError):
        ed = ldt_tower["Data"][-1].strftime("%Y-%m-%d %H:%M")
    l4a["gui"]["enddate"] = ed
    return

def parse_gfMDS_createdict(cf, ds, l5_info, label, called_by, flag_code):
    """
    Purpose:
     Create an information dictionary for MDS gap filling from the contents
     of the control file.
    Usage:
     gfMDS_createdict(cf, ds, l5_info, label, called_by)
    Author: PRI
    Date: May 2018
    """
    # create the solo settings directory
    if called_by not in l5_info:
        l5_info[called_by] = {"outputs": {}, "info": {}}
    # file path and input file name
    l5_info[called_by]["info"]["file_path"] = cf["Files"]["file_path"]
    l5_info[called_by]["info"]["in_filename"] = cf["Files"]["in_filename"]
    # get the executable suffix
    l5_info[called_by]["info"]["executable_suffix"] = pfp_utils.get_executable_suffix()
    # get the plot path
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="./plots/")
    plot_path = os.path.join(opt, "L5", "")
    if not os.path.exists(plot_path):
        try:
            os.makedirs(plot_path)
        except OSError:
            msg = "Unable to create the plot path " + plot_path + "\n"
            msg = msg + "Press 'Quit' to edit the control file.\n"
            msg = msg + "Press 'Continue' to use the default path.\n"
            result = pfp_gui.MsgBox_ContinueOrQuit(msg, title="Warning: L5 plot path")
            if result.clickedButton().text() == "Quit":
                # user wants to edit the control file
                msg = " Quitting L5 to edit control file"
                logger.warning(msg)
                ds.info["returncodes"]["message"] = msg
                ds.info["returncodes"]["value"] = 1
            else:
                plot_path = "./plots/"
                cf["Files"]["plot_path"] = "./plots/"
    l5_info[called_by]["info"]["plot_path"] = plot_path
    # get the maximum length for "short" gaps in days
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "MaxShortGapDays", default=14)
    max_short_gap_days = int(opt)
    l5_info[called_by]["info"]["MaxShortGapDays"] = max_short_gap_days
    # maximum length in records
    ts = int(float(ds.root["Attributes"]["time_step"]))
    nperday = 24 * 60//ts
    l5_info[called_by]["info"]["MaxShortGapRecords"] = max_short_gap_days * nperday
    # name of MDS output series in ds
    outputs = list(cf["Fluxes"][label]["GapFillUsingMDS"].keys())
    # loop over the outputs listed in the control file
    l5mo = l5_info[called_by]["outputs"]
    for output in outputs:
        # disable output to netCDF file for this variable
        if output not in list(cf["Fluxes"].keys()):
            l5_info["RemoveIntermediateSeries"]["not_output"].append(output)
        # create the dictionary keys for this series
        l5mo[output] = {}
        # get the target
        if "target" in cf["Fluxes"][label]["GapFillUsingMDS"][output]:
            l5mo[output]["target"] = cf["Fluxes"][label]["GapFillUsingMDS"][output]["target"]
        else:
            l5mo[output]["target"] = label
        # list of MDS settings
        if "mds_settings" in cf["Fluxes"][label]["GapFillUsingMDS"][output]:
            mdss_string = cf["Fluxes"][label]["GapFillUsingMDS"][output]["mds_settings"]
            mdss_string = mdss_string.replace(" ","")
            if "," in mdss_string:
                l5mo[output]["mds_settings"] = mdss_string.split(",")
            else:
                l5mo[output]["mds_settings"] = [mdss_string]
        # list of drivers
        drivers_string = cf["Fluxes"][label]["GapFillUsingMDS"][output]["drivers"]
        drivers_string = drivers_string.replace(" ","")
        if "," in drivers_string:
            if len(drivers_string.split(",")) == 3:
                l5mo[output]["drivers"] = drivers_string.split(",")
                # append to list of drivers to be checked for gaps
                l5_info["CheckDrivers"]["drivers"] += drivers_string.split(",")
            else:
                msg = " MDS: incorrect number of drivers for " + label + ", skipping ..."
                logger.error(msg)
                continue
        else:
            msg = " MDS: incorrect number of drivers for " + label + ", skipping ..."
            logger.error(msg)
            continue
        # list of tolerances
        tolerances_string = cf["Fluxes"][label]["GapFillUsingMDS"][output]["tolerances"]
        tolerances_string = tolerances_string.replace(" ","")
        tolerances_string = tolerances_string.replace("(","").replace(")","")
        if "," in tolerances_string:
            if len(tolerances_string.split(",")) == 4:
                parts = tolerances_string.split(",")
                l5mo[output]["tolerances"] = [(parts[0], parts[1]), parts[2], parts[3]]
            else:
                msg = " MDS: incorrect format for tolerances for " + label + ", skipping ..."
                logger.error(msg)
                continue
        else:
            msg = " MDS: incorrect format for tolerances for " + label + ", skipping ..."
            logger.error(msg)
            continue
    # check that all requested targets and drivers have a mapping to
    # a FluxNet label, remove if they don't
    fluxnet_label_map = {"Fco2":"NEE", "Fe":"LE", "Fh":"H",
                         "Fsd":"SW_IN", "Ta":"TA", "VPD":"VPD"}
    for mds_label in list(l5_info[called_by]["outputs"]):
        l5_info[called_by]["outputs"][mds_label]["mds_label"] = mds_label
        pfp_target = l5_info[called_by]["outputs"][mds_label]["target"]
        if pfp_target not in fluxnet_label_map:
            msg = " Target ("+pfp_target+") not supported for MDS gap filling"
            logger.warning(msg)
            del l5_info[called_by]["outputs"][mds_label]
            continue
        else:
            l5_info[called_by]["outputs"][mds_label]["target_mds"] = fluxnet_label_map[pfp_target]
        pfp_drivers = l5_info[called_by]["outputs"][mds_label]["drivers"]
        for pfp_driver in pfp_drivers:
            if pfp_driver not in fluxnet_label_map:
                msg = "Driver ("+pfp_driver+") not supported for MDS gap filling"
                logger.warning(msg)
                l5_info[called_by]["outputs"][mds_label]["drivers"].remove(pfp_driver)
            else:
                if "drivers_mds" not in l5_info[called_by]["outputs"][mds_label]:
                    l5_info[called_by]["outputs"][mds_label]["drivers_mds"] = []
                l5_info[called_by]["outputs"][mds_label]["drivers_mds"].append(fluxnet_label_map[pfp_driver])
        if len(l5_info[called_by]["outputs"][mds_label]["drivers"]) == 0:
            del l5_info[called_by]["outputs"][mds_label]
            continue
    return

def parse_gfMergeSeries_createdict(cf, ds, info, label, called_by):
    """ Creates a dictionary in ds to hold information about the merging of gap filled
        and tower data."""
    merge_prereq_list = ["Fsd","Fsu","Fld","Flu","Ts","Sws"]
    # get the section of the control file containing the series
    section = pfp_utils.get_cfsection(cf, label, mode="quiet")
    # create the merge directory in the data structure
    if called_by not in info:
        info[called_by] = {}
    # check to see if this series is in the "merge first" list
    # series in the "merge first" list get merged first so they can be used with existing tower
    # data to re-calculate Fg, Fn and Fa
    merge_order = "standard"
    if label in merge_prereq_list:
        merge_order = "prerequisite"
    if merge_order not in list(info[called_by].keys()):
        info[called_by][merge_order] = {}
    # create the dictionary keys for this series
    info[called_by][merge_order][label] = {}
    # output series name
    info[called_by][merge_order][label]["output"] = label
    # merge source list
    section = pfp_utils.get_cfsection(cf, label, mode="quiet")
    src_list = pfp_utils.GetMergeSeriesKeys(cf, label, section=section)
    info[called_by][merge_order][label]["source"] = src_list
    # create an empty series in ds if the output series doesn't exist yet
    if label not in list(ds.root["Variables"].keys()):
        nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
        var = pfp_utils.CreateEmptyVariable(label, nrecs)
        pfp_utils.CreateVariable(ds, var)
    return

def parse_gfSOLO_createdict(cf, ds, l5_info, target_label, called_by, flag_code):
    """
    Purpose:
     Creates a dictionary in l5_info to hold information about the SOLO data
     used to gap fill the tower data.
    Usage:
    Side effects:
    Author: PRI
    Date: August 2014
    """
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    # make the L5 "description" attrubute for the target variable
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    ds.root["Variables"][target_label]["Attr"][descr_level] = ""
    # create the solo settings directory
    if called_by not in list(l5_info.keys()):
        # create the GapFillUsingSOLO dictionary
        l5_info[called_by] = {"outputs": {}, "info": {}, "gui": {}}
        # only need to create the ["info"] dictionary on the first pass
        parse_gfSOLO_createdict_info(cf, ds, l5_info, called_by)
        if ds.info["returncodes"]["value"] != 0:
            return
        # only need to create the ["gui"] dictionary on the first pass
        parse_gfSOLO_createdict_gui(cf, ds, l5_info, called_by)
    # get the outputs section
    parse_gfSOLO_createdict_outputs(cf, l5_info, target_label, called_by, flag_code)
    # add the summary plors section
    if "SummaryPlots" in cf:
        l5_info[called_by]["SummaryPlots"] = cf["SummaryPlots"]
    # create an empty series in ds if the SOLO output series doesn't exist yet
    outputs = list(cf["Fluxes"][target_label][called_by].keys())
    for output in outputs:
        l5_info["CheckDrivers"]["drivers"] += l5_info[called_by]["outputs"][output]["drivers"]
        if output not in list(ds.root["Variables"].keys()):
            # disable output to netCDF file for this variable
            l5_info["RemoveIntermediateSeries"]["not_output"].append(output)
            # create an empty variable
            variable = pfp_utils.CreateEmptyVariable(output, nrecs)
            # update the empty variable attributes
            target_variable = pfp_utils.GetVariable(ds, target_label)
            for vattr in ["long_name", "valid_range", "units", "standard_name"]:
                if vattr in target_variable["Attr"]:
                    variable["Attr"][vattr] = target_variable["Attr"][vattr]
            # create L5 specific vards.root["Variables"][label]iable attributes
            variable["Attr"]["drivers"] = l5_info[called_by]["outputs"][output]["drivers"]
            variable["Attr"]["target"] = target_label
            pfp_utils.append_to_attribute(variable["Attr"], {descr_level: "SOLO"})
            pfp_utils.CreateVariable(ds, variable)
    return

def parse_gfSOLO_createdict_gui(cf, ds, l5_info, called_by):
    """
    Purpose:
     Get settings for the GapFillUsingSOLO routine from the [GUI]
     section of the L5 control file.
    Usage:
    Side effects:
    Author: PRI
    Date: August 2019
    """
    # local pointer to l5_info[called_by]
    l5s = l5_info[called_by]
    # local pointer to datetime
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    # populate the l5_info["gui"] dictionary with things that will be useful
    ts = int(float(ds.root["Attributes"]["time_step"]))
    # number of records per hour and per day
    l5s["gui"]["nperhr"] = int(float(60)/ts + 0.5)
    l5s["gui"]["nperday"] = int(float(24)*l5s["gui"]["nperhr"] + 0.5)
    # items from the [GUI] section of the control file
    sl = ["GUI", called_by]
    # window length
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "period_option", default="manual")
    if opt == "manual":
        l5s["gui"]["period_option"] = 1
    elif opt == "monthly":
        l5s["gui"]["period_option"] = 2
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "number_months", default=2)
        l5s["gui"]["number_months"] = int(opt)
    elif opt == "days":
        l5s["gui"]["period_option"] = 3
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "number_days", default=60)
        l5s["gui"]["number_days"] = int(opt)
    # overwrite option
    l5s["gui"]["overwrite"] = False
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "overwrite", default="no")
    if opt.lower() == "yes": l5s["gui"]["overwrite"] = True
    # show plots option
    if cf["Options"]["call_mode"].lower() == "interactive":
        l5s["gui"]["show_plots"] = True
    else:
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "show_plots", default="no")
        if opt.lower() == "no":
            l5s["gui"]["show_plots"] = False
    # show all plots option
    l5s["gui"]["show_all"] = False
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "show_all", default="no")
    if opt.lower() == "yes": l5s["gui"]["show_all"] = True
    # auto-complete option
    l5s["gui"]["auto_complete"] = True
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "auto_complete", default="yes")
    if opt.lower() == "no": l5s["gui"]["auto_complete"] = False
    # minimum percentage of good points required
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "min_percent", default=50)
    l5s["gui"]["min_percent"] = max(int(opt), 1)
    # nodes for SOFM/SOLO network
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "nodes", default="auto")
    l5s["gui"]["nodes"] = str(opt)
    # training iterations
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "training", default="500")
    l5s["gui"]["training"] = str(opt)
    # nda factor
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "nda_factor", default="5")
    l5s["gui"]["nda_factor"] = str(opt)
    # learning rate
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "learning_rate", default="0.001")
    l5s["gui"]["learning_rate"] = str(opt)
    # learning iterations
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "iterations", default="500")
    l5s["gui"]["iterations"] = str(opt)
    # start date of period to be gap filled
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "start_date", default="YYYY-MM-DD HH:mm")
    try:
        sd = dateutil.parser.parse(opt)
    except (ValueError, TypeError):
        #sd = ldt["Data"][0].strftime("%Y-%m-%d %H:%M")
        sd = ldt["Data"][0]
    l5s["gui"]["startdate"] = sd
    # end date of period to be gap filled
    opt = pfp_utils.get_keyvaluefromcf(cf, sl, "end_date", default="YYYY-MM-DD HH:mm")
    try:
        ed = dateutil.parser.parse(opt)
    except (ValueError, TypeError):
        #ed = ldt["Data"][-1].strftime("%Y-%m-%d %H:%M")
        ed = ldt["Data"][-1]
    l5s["gui"]["enddate"] = ed
    return

def parse_gfSOLO_createdict_info(cf, ds, l5_info, called_by):
    """
    Purpose:
     Create the "info" section of the l5_info[called_by] dictionary.
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
          June 2019 - modified for new l5_info structure
    """
    l5s = l5_info[called_by]
    # reset the return message and code
    ds.info["returncodes"]["message"] = "OK"
    ds.info["returncodes"]["value"] = 0
    # time step
    time_step = int(float(ds.root["Attributes"]["time_step"]))
    # get the level of processing
    level = ds.root["Attributes"]["processing_level"]
    # local pointer to the datetime series
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    # add an info section to the l5_info[called_by] dictionary
    #l5s["info"]["file_startdate"] = ldt[0].strftime("%Y-%m-%d %H:%M")
    #l5s["info"]["file_enddate"] = ldt[-1].strftime("%Y-%m-%d %H:%M")
    l5s["info"]["startdate"] = ldt[0].strftime("%Y-%m-%d %H:%M")
    l5s["info"]["enddate"] = ldt[-1].strftime("%Y-%m-%d %H:%M")
    l5s["info"]["called_by"] = called_by
    l5s["info"]["time_step"] = time_step
    l5s["info"]["site_name"] = ds.root["Attributes"]["site_name"]
    l5s["info"]["executable_suffix"] = pfp_utils.get_executable_suffix()
    # check to see if this is a batch or an interactive run
    call_mode = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "call_mode", default="interactive")
    l5s["info"]["call_mode"] = call_mode
    # truncate to last date in Imports?
    truncate = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "TruncateToImports", default="Yes")
    l5s["info"]["truncate_to_imports"] = truncate
    # number of records per day and maximum lags
    nperhr = int(float(60)/time_step + 0.5)
    l5s["info"]["nperday"] = int(float(24)*nperhr + 0.5)
    l5s["info"]["maxlags"] = int(float(12)*nperhr + 0.5)
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
            title = "Warning: " + level + " plot path"
            result = pfp_gui.MsgBox_ContinueOrQuit(msg, title=title)
            if result.clickedButton().text() == "Quit":
                # user wants to edit the control file
                msg = " Quitting " + level + " to edit control file"
                logger.warning(msg)
                ds.info["returncodes"]["message"] = msg
                ds.info["returncodes"]["value"] = 1
            else:
                plot_path = "./plots/"
                cf["Files"]["plot_path"] = "./plots/"
    l5s["info"]["plot_path"] = plot_path
    return

def parse_gfSOLO_createdict_outputs(cf, l5_info, target, called_by, flag_code):
    """
    Purpose:
     Create the l5_info[called_by]["outputs"] dictionary.
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
        August 2019 - rewritten for consistency and batch operation
    """
    iris = l5_info["RemoveIntermediateSeries"]
    so = l5_info[called_by]["outputs"]
    # loop over the outputs listed in the control file
    if ((called_by == "GapFillUsingSOLO") or
        (called_by == "GapFillLongSOLO")):
        section = "Fluxes"
        drivers = "Fn,Fg,SHD,SH,Ta,Ts"
        source = target
    elif called_by == "ERUsingSOLO":
        section = "EcosystemRespiration"
        drivers = "Ta,Ts,Sws"
        source = target
    else:
        msg = "Unrecognised calling routine"
        logger.error(msg)
        return
    outputs = list(cf[section][target][called_by].keys())
    for output in outputs:
        # disable output to netCDF file for this variable
        iris["not_output"].append(output)
        # create the dictionary keys for this series
        so[output] = {}
        # get the target
        sl = [section, target, called_by, output]
        so[output]["target"] = pfp_utils.get_keyvaluefromcf(cf, sl, "target", default=target)
        so[output]["source"] = pfp_utils.get_keyvaluefromcf(cf, sl, "source", default=source)
        # add the flag_code
        so[output]["flag_code"] = flag_code
        # list of SOLO settings
        if "solo_settings" in cf[section][target][called_by][output]:
            src_string = cf[section][target][called_by][output]["solo_settings"]
            src_list = src_string.split(",")
            so[output]["solo_settings"] = {}
            so[output]["solo_settings"]["nodes_target"] = int(src_list[0])
            so[output]["solo_settings"]["training"] = int(src_list[1])
            so[output]["solo_settings"]["nda_factor"] = int(src_list[2])
            so[output]["solo_settings"]["learning_rate"] = float(src_list[3])
            so[output]["solo_settings"]["iterations"] = int(src_list[4])
        # list of drivers
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "drivers", default=drivers)
        so[output]["drivers"] = pfp_utils.string_to_list(opt)
        # fit statistics for plotting later on
        so[output]["results"] = {"startdate": [], "middate": [],"enddate": [], "No. points": [],
                                 "r": [], "Bias": [], "RMSE": [], "Frac Bias": [], "NMSE": [],
                                 "Avg (obs)": [], "Avg (SOLO)": [],
                                 "Var (obs)": [], "Var (SOLO)": [], "Var ratio": [],
                                 "m_ols": [], "b_ols": []}
    return

def ParseL5ControlFile(cfg, ds):
    """
    Purpose:
     Create the L5 information and setting dictionary.
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
    """
    ds.info["returncodes"]["message"] = "OK"
    ds.info["returncodes"]["value"] = 0
    l5_info = {}
    l5_info["cfg"] = copy.deepcopy(cfg)
    # add keys for turbulence filter
    l5_info["ApplyTurbulenceFilter"] = {}
    turbulence_filter = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "TurbulenceFilter", default="ustar (basic)")
    l5_info["ApplyTurbulenceFilter"]["turbulence_filter"] = turbulence_filter
    accept_day_times = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "AcceptDayTimes", default="Yes")
    l5_info["ApplyTurbulenceFilter"]["accept_day_times"] = accept_day_times
    filter_string = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "FilterList", default="Fco2")
    l5_info["ApplyTurbulenceFilter"]["filter_list"] = filter_string.split(",")
    # add key for suppressing output of intermediate variables e.g. Ta_aws
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "KeepIntermediateSeries", default="No")
    l5_info["RemoveIntermediateSeries"] = {"KeepIntermediateSeries": opt, "not_output": []}
    # add key for interpolation
    interpolate_type = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "InterpolateType", default="Akima")
    max_gap_interpolate = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "MaxGapInterpolate", default=3)
    l5_info["GapFillUsingInterpolation"] = {"InterpolateType": str(interpolate_type),
                                            "MaxGapInterpolate": int(max_gap_interpolate)}
    # get a list of targets being gap filled, this may not simply be a list of keys
    # in the control file if 'target' is specified in the gap filling method
    targets = list(cfg["Fluxes"].keys())
    gf_methods = []
    for target in list(targets):
        gf_methods = [m for m in cfg["Fluxes"][target].keys() if m != "MergeSeries"]
        gf_method_targets = []
        for gf_method in list(gf_methods):
            gf_method_labels = list(cfg["Fluxes"][target][gf_method].keys())
            for gf_method_label in list(gf_method_labels):
                if "target" in cfg["Fluxes"][target][gf_method][gf_method_label]:
                    real_target = cfg["Fluxes"][target][gf_method][gf_method_label]["target"]
                    gf_method_targets.append(real_target)
                    targets[targets.index(target)] = real_target
    targets = targets + gf_method_targets
    targets = sorted(list(set(targets)))
    l5_info["GapFillUsingInterpolation"]["targets"] = targets.copy()
    l5_info["CheckTargets"] = {"targets": targets.copy()}
    l5_info["CheckDrivers"] = {"drivers": []}
    # get a list of keys in the control file
    labels = sorted(list(cfg["Fluxes"].keys()))
    for label in labels:
        if "GapFillUsingSOLO" in list(cfg["Fluxes"][label].keys()):
            parse_gfSOLO_createdict(cfg, ds, l5_info, label, "GapFillUsingSOLO", 510)
            # check to see if something went wrong
            if ds.info["returncodes"]["value"] != 0:
                # if it has, return to calling routine
                return l5_info
        if "GapFillLongSOLO" in list(cfg["Fluxes"][label].keys()):
            parse_gfSOLO_createdict(cfg, ds, l5_info, label, "GapFillLongSOLO", 520)
            if ds.info["returncodes"]["value"] != 0:
                return l5_info
        if "GapFillUsingMDS" in list(cfg["Fluxes"][label].keys()):
            parse_gfMDS_createdict(cfg, ds, l5_info, label, "GapFillUsingMDS", 530)
            if ds.info["returncodes"]["value"] != 0:
                return l5_info
        if "MergeSeries" in list(cfg["Fluxes"][label].keys()):
            parse_gfMergeSeries_createdict(cfg, ds, l5_info, label, "MergeSeries")
    l5_info["CheckDrivers"]["drivers"] = list(set(l5_info["CheckDrivers"]["drivers"]))
    return l5_info

def ParseL6ControlFile(cfg, ds):
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
    l6_info["cfg"] = copy.deepcopy(cfg)
    # summary section
    l6_info["Summary"] = {"EcosystemRespiration":[],
                          "NetEcosystemExchange": [],
                          "GrossPrimaryProductivity": []}
    # merge section
    l6_info["MergeSeries"] = {"standard": {}}
    # propagate the ['Files'] section
    l6_info["Files"] = copy.deepcopy(cfg["Files"])
    # propagate the ['Options'] section
    l6_info["Options"] = copy.deepcopy(cfg["Options"])
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "Fsd_threshold", default=10)
    l6_info["Options"]["noct_threshold"] = int(float(opt))
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "ConvertToPhotons", default=True)
    l6_info["Options"]["convert_to_photons"] = opt
    l6_info["Options"]["plot_raw_data"] = False
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "PlotRawData", default="No")
    if opt.lower() == "yes":
        l6_info["Options"]["plot_raw_data"] = True
    # some useful global attributes
    l6_info["Global"] = {"site_name": ds.root["Attributes"]["site_name"],
                         "time_step": int(float(ds.root["Attributes"]["time_step"]))}
    # add key for suppressing output of intermediate variables e.g. Ta_aws
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "KeepIntermediateSeries", default="No")
    l6_info["RemoveIntermediateSeries"] = {"KeepIntermediateSeries": opt, "not_output": []}
    if "EcosystemRespiration" in list(cfg.keys()):
        l6_info["EcosystemRespiration"] = copy.deepcopy(cfg["EcosystemRespiration"])
        for output in list(cfg["EcosystemRespiration"].keys()):
            if "ERUsingSOLO" in list(cfg["EcosystemRespiration"][output].keys()):
                parse_rpSOLO_createdict(cfg, ds, l6_info, output, "ERUsingSOLO", 610)
            if "ERUsingLloydTaylor" in list(cfg["EcosystemRespiration"][output].keys()):
                parse_rp_createdict(cfg, ds, l6_info, output, "ERUsingLloydTaylor", 620)
            if "ERUsingLasslop" in list(cfg["EcosystemRespiration"][output].keys()):
                parse_rp_createdict(cfg, ds, l6_info, output, "ERUsingLasslop", 630)
    if "NetEcosystemExchange" in list(cfg.keys()):
        l6_info["NetEcosystemExchange"] = {}
        for output in list(cfg["NetEcosystemExchange"].keys()):
            parse_rpNEE_createdict(cfg, ds, l6_info["NetEcosystemExchange"], output)
    if "GrossPrimaryProductivity" in list(cfg.keys()):
        l6_info["GrossPrimaryProductivity"] = {}
        for output in list(cfg["GrossPrimaryProductivity"].keys()):
            parse_rpGPP_createdict(cfg, ds, l6_info["GrossPrimaryProductivity"], output)
    if "EvapoTranspiration" in list(cfg.keys()):
        l6_info["EvapoTranspiration"] = copy.deepcopy(cfg["EvapoTranspiration"])
    return l6_info

def ParseL7ControlFile(cfg, ds):
    """
    Purpose:
     Parse the L7 control file and return contents in the l7_info dictionary.
    Usage:
    Side effects:
    Author: PRI
    Date: February 2024
    """
    l7_info = {}
    l7_info["cfg"] = copy.deepcopy(cfg)
    l7_info["Summary"] = {"EcosystemRespiration":[],
                          "NetEcosystemExchange": [],
                          "GrossPrimaryProductivity": []}
    l7_info["MergeSeries"] = {"standard": {}}
    l7_info["Files"] = copy.deepcopy(cfg["Files"])
    # propagate the ['Options'] section
    l7_info["Options"] = copy.deepcopy(cfg["Options"])
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "Fsd_threshold", default=10)
    l7_info["Options"]["noct_threshold"] = int(float(opt))
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "ConvertToPhotons", default=True)
    l7_info["Options"]["convert_to_photons"] = opt
    l7_info["Options"]["plot_raw_data"] = False
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "PlotRawData", default="No")
    if opt.lower() == "yes":
        l7_info["Options"]["plot_raw_data"] = True
    l7_info["Options"]["multiprocessing"] = False
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "MultiProcessing", default="Yes")
    if opt.lower() == "yes":
        l7_info["Options"]["multiprocessing"] = True
    # some useful global attributes
    l7_info["Global"] = {"site_name": ds.root["Attributes"]["site_name"],
                         "time_step": int(float(ds.root["Attributes"]["time_step"]))}
    l7_info["ApplyTurbulenceFilter"] = {}
    turbulence_filter = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "TurbulenceFilter", default="ustar (basic)")
    l7_info["ApplyTurbulenceFilter"]["turbulence_filter"] = turbulence_filter
    accept_day_times = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "AcceptDayTimes", default="Yes")
    l7_info["ApplyTurbulenceFilter"]["accept_day_times"] = accept_day_times
    filter_string = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "FilterList", default="Fco2")
    l7_info["ApplyTurbulenceFilter"]["filter_list"] = filter_string.split(",")
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "KeepIntermediateSeries", default="No")
    l7_info["RemoveIntermediateSeries"] = {"KeepIntermediateSeries": opt, "not_output": []}
    # options for estimating random uncertainty
    l7_info["EstimateRandomUncertainty"] = {}
    l7_info["EstimateRandomUncertainty"]["labels"] = ["Fco2", "Fe", "Fh"]
    l7_info["EstimateRandomUncertainty"]["Method1"] = {"window_size": 14, "hour_range": 1,
                                                       "Fsd": {"tolerance": [20, 50]},
                                                       "Ta": {"tolerance": 2.5},
                                                       "VPD": {"tolerance": 0.5}}
    l7_info["EstimateRandomUncertainty"]["Method2"] = {"window_size": 28,
                                                       "Fco2" : {"tolerance": 0.2, "limit": 2},
                                                       "Fe" : {"tolerance": 0.2, "limit": 25},
                                                       "Fh" : {"tolerance": 0.2, "limit": 25}}
    # add key for interpolation
    interpolate_type = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "InterpolateType", default="Akima")
    max_gap_interpolate = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "MaxGapInterpolate", default=3)
    l7_info["GapFillUsingInterpolation"] = {"InterpolateType": str(interpolate_type),
                                            "MaxGapInterpolate": int(max_gap_interpolate)}
    # get a list of targets being gap filled, this may not simply be a list of keys
    # in the control file if 'target' is specified in the gap filling method
    targets = list(cfg["Fluxes"].keys())
    gf_methods = []
    for target in list(targets):
        gf_methods = [m for m in cfg["Fluxes"][target].keys() if m != "MergeSeries"]
        gf_method_targets = []
        for gf_method in list(gf_methods):
            gf_method_labels = list(cfg["Fluxes"][target][gf_method].keys())
            for gf_method_label in list(gf_method_labels):
                if "target" in cfg["Fluxes"][target][gf_method][gf_method_label]:
                    real_target = cfg["Fluxes"][target][gf_method][gf_method_label]["target"]
                    gf_method_targets.append(real_target)
                    targets[targets.index(target)] = real_target
    targets = targets + gf_method_targets
    targets = sorted(list(set(targets)))
    l7_info["GapFillUsingInterpolation"]["targets"] = targets.copy()
    l7_info["CheckTargets"] = {"targets": targets.copy()}
    l7_info["CheckDrivers"] = {"drivers": []}
    labels = sorted(list(cfg["Fluxes"].keys()))
    for label in labels:
        if "GapFillUsingSOLO" in list(cfg["Fluxes"][label].keys()):
            parse_gfSOLO_createdict(cfg, ds, l7_info, label, "GapFillUsingSOLO", 710)
        if "GapFillLongSOLO" in list(cfg["Fluxes"][label].keys()):
            parse_gfSOLO_createdict(cfg, ds, l7_info, label, "GapFillLongSOLO", 720)
        if "GapFillUsingMDS" in list(cfg["Fluxes"][label].keys()):
            parse_gfMDS_createdict(cfg, ds, l7_info, label, "GapFillUsingMDS", 730)
        if "MergeSeries" in list(cfg["Fluxes"][label].keys()):
            parse_gfMergeSeries_createdict(cfg, ds, l7_info, label, "MergeSeries")
    if "EcosystemRespiration" in list(cfg.keys()):
        l7_info["EcosystemRespiration"] = copy.deepcopy(cfg["EcosystemRespiration"])
        for output in list(cfg["EcosystemRespiration"].keys()):
            if "ERUsingSOLO" in list(cfg["EcosystemRespiration"][output].keys()):
                parse_rpSOLO_createdict(cfg, ds, l7_info, output, "ERUsingSOLO", 740)
            if "ERUsingLloydTaylor" in list(cfg["EcosystemRespiration"][output].keys()):
                parse_rp_createdict(cfg, ds, l7_info, output, "ERUsingLloydTaylor", 750)
            if "ERUsingLasslop" in list(cfg["EcosystemRespiration"][output].keys()):
                parse_rp_createdict(cfg, ds, l7_info, output, "ERUsingLasslop", 760)
    if "NetEcosystemExchange" in list(cfg.keys()):
        l7_info["NetEcosystemExchange"] = {}
        for output in list(cfg["NetEcosystemExchange"].keys()):
            parse_rpNEE_createdict(cfg, ds, l7_info["NetEcosystemExchange"], output)
    if "GrossPrimaryProductivity" in list(cfg.keys()):
        l7_info["GrossPrimaryProductivity"] = {}
        for output in list(cfg["GrossPrimaryProductivity"].keys()):
            parse_rpGPP_createdict(cfg, ds, l7_info["GrossPrimaryProductivity"], output)
    # set the batch/interactive mode and show plots switches
    l7_info["GapFillUsingSOLO"]["info"]["call_mode"] = "batch"
    l7_info["GapFillUsingSOLO"]["gui"]["show_plots"] = False
    l7_info["ERUsingSOLO"]["info"]["call_mode"] = "batch"
    l7_info["ERUsingSOLO"]["gui"]["show_plots"] = False
    l7_info["ERUsingLloydTaylor"]["gui"]["show_plots"] = False
    l7_info["ERUsingLasslop"]["gui"]["show_plots"] = False
    return l7_info

def parse_rp_createdict(cf, ds, l6_info, output, called_by, flag_code):
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
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    # create the settings directory
    if called_by not in l6_info.keys():
        l6_info[called_by] = {"outputs": {}, "info": {}, "gui": {}}
    # get the info section
    parse_rp_createdict_info(cf, ds, l6_info, called_by)
    if ds.info["returncodes"]["value"] != 0:
        return
    # get the outputs section
    parse_rp_createdict_outputs(cf, l6_info, output, called_by, flag_code)
    # create an empty series in ds if the output series doesn't exist yet
    Fc = pfp_utils.GetVariable(ds, l6_info[called_by]["info"]["source"])
    model_outputs = cf["EcosystemRespiration"][output][called_by].keys()
    for model_output in model_outputs:
        if model_output not in ds.root["Variables"].keys():
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

def parse_rp_createdict_info(cf, ds, l6_info, called_by):
    """
    Purpose:
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
          June 2019 - modified for new l5_info structure
    """
    erl = l6_info[called_by]
    # Create a dict to set the file_suffix and extension
    suffix_dict = {'ERUsingLasslop': "_Lasslop.xlsx",
                   'ERUsingLloydTaylor': "_LloydTaylor.xlsx"}
    # reset the return message and code
    ds.info["returncodes"]["message"] = "OK"
    ds.info["returncodes"]["value"] = 0
    # time step
    time_step = int(ds.root["Attributes"]["time_step"])
    # get the level of processing
    level = ds.root["Attributes"]["processing_level"]
    # local pointer to the datetime series
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    # add an info section to the info["solo"] dictionary
    #erl["info"]["file_startdate"] = ldt[0].strftime("%Y-%m-%d %H:%M")
    #erl["info"]["file_enddate"] = ldt[-1].strftime("%Y-%m-%d %H:%M")
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
                ds.info["returncodes"]["message"] = msg
                ds.info["returncodes"]["value"] = 1
            else:
                plot_path = "./plots/"
                cf["Files"]["plot_path"] = "./plots/"
    erl["info"]["plot_path"] = plot_path
    erl["info"]["sheet_suffix"] = ""
    return

def parse_rp_createdict_outputs(cf, l6_info, target, called_by, flag_code):
    """Where's the docstring ya bastard?!"""
    erl = l6_info[called_by]
    var_dict = {'ERUsingLasslop': "LL",
                'ERUsingLloydTaylor': "LT"}
    eo = erl["outputs"]
    # loop over the outputs listed in the control file
    section = "EcosystemRespiration"
    outputs = cf[section][target][called_by].keys()
    for output in outputs:
        # add the output label to intermediate series
        l6_info["RemoveIntermediateSeries"]["not_output"].append(output)
        # create the dictionary keys for this series
        eo[output] = {}
        # get the output options
        for key in list(cf[section][target][called_by][output].keys()):
            eo[output][key] = cf[section][target][called_by][output][key]
        # update the target and source
        sl = [section, target, called_by, output]
        eo[output]["target"] = pfp_utils.get_keyvaluefromcf(cf, sl, "target", default=target)
        eo[output]["source"] = pfp_utils.get_keyvaluefromcf(cf, sl, "source", default=target)
        # add the flag_code
        eo[output]["flag_code"] = flag_code
        # list of drivers
        # ERUsingLloydTaylor can have 2 temperaturres e.g. Ta and Ts
        max_drivers = 2
        if called_by in ["ERUsingLasslop"]:
            # ERUsingLasslop can have 4 e.g. Fsd, VPD, Ta and Ts
            max_drivers = 4
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "drivers", default="Ta")
        if len(pfp_utils.string_to_list(opt)) <= max_drivers:
            eo[output]["drivers"] = pfp_utils.string_to_list(opt)
        else:
            msg = " Too many drivers specified (only alowed " + str(max_drivers) + "), using Ta"
            logger.error(msg)
            eo[output]["drivers"] = pfp_utils.string_to_list("Ta")
        # weighting for air temperature, soil temperature or combination
        drivers = [d for d in eo[output]["drivers"] if d[0:2] in ["Ta", "Ts"]]
        if len(drivers) == 1:
            eo[output]["weighting"] = pfp_utils.string_to_list("1.0")
        elif len(drivers) == 2:
            default = "0.5,0.5"
            opt = pfp_utils.get_keyvaluefromcf(cf, sl, "weighting", default=default)
            eo[output]["weighting"] = pfp_utils.string_to_list(opt)
        else:
            msg = " Too many temperatures as drivers (only allowed 2), using Ta"
            eo[output]["drivers"] = pfp_utils.string_to_list("Ta")
            eo[output]["weighting"] = pfp_utils.string_to_list("1.0")
        opt = pfp_utils.get_keyvaluefromcf(cf, sl, "output_plots", default="False")
        eo[output]["output_plots"] = (opt == "True")
        # fit statistics for plotting later on
        eo[output]["results"] = {"startdate":[],"enddate":[],"No. points":[],"r":[],
                                 "Bias":[],"RMSE":[],"Frac Bias":[],"NMSE":[],
                                 "Avg (obs)":[],"Avg (" + var_dict[called_by] + ")":[],
                                 "Var (obs)":[],"Var (" + var_dict[called_by] + ")":[],"Var ratio":[],
                                 "m_ols":[],"b_ols":[]}
    return

def parse_rpGPP_createdict(cf, ds, info, label):
    """ Creates a dictionary in ds to hold information about calculating GPP."""
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
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
    if info[label]["output"] not in list(ds.root["Variables"].keys()):
        var = pfp_utils.CreateEmptyVariable(info[label]["output"], nrecs)
        pfp_utils.CreateVariable(ds, var)
    return

def parse_rpNEE_createdict(cf, ds, info, label):
    """ Creates a dictionary in ds to hold information about calculating NEE."""
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
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
    if info[label]["output"] not in list(ds.root["Variables"].keys()):
        var = pfp_utils.CreateEmptyVariable(info[label]["output"], nrecs)
        pfp_utils.CreateVariable(ds, var)
    return

def parse_rpSOLO_createdict(cf, ds, l6_info, output, called_by, flag_code):
    """
    Purpose:
     Creates a dictionary in l6_info to hold information about the SOLO data
     used to estimate ecosystem respiration.
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day
    """
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    # make the L6 "description" attrubute for the target variable
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    # create the dictionary keys for this series
    if called_by not in list(l6_info.keys()):
        l6_info[called_by] = {"outputs": {}, "info": {"source": "Fco2", "target": "ER"}, "gui": {}}
        # only need to create the ["info"] dictionary on the first pass
        parse_gfSOLO_createdict_info(cf, ds, l6_info, called_by)
        if ds.info["returncodes"]["value"] != 0:
            return
        # only need to create the ["gui"] dictionary on the first pass
        parse_gfSOLO_createdict_gui(cf, ds, l6_info, called_by)
    # get the outputs section
    parse_gfSOLO_createdict_outputs(cf, l6_info, output, called_by, flag_code)
    # create an empty series in ds if the SOLO output series doesn't exist yet
    Fco2 = pfp_utils.GetVariable(ds, l6_info[called_by]["info"]["source"])
    model_outputs = list(cf["EcosystemRespiration"][output][called_by].keys())
    for model_output in model_outputs:
        if model_output not in list(ds.root["Variables"].keys()):
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

def parse_variable_attributes(attributes):
    """
    Purpose:
     Clean up the variable attributes.
    Usage:
    Author: PRI
    Date: September 2019
    """
    for attr in attributes:
        value = attributes[attr]
        if not isinstance(value, str):
            continue
        if attr in ["rangecheck_lower", "rangecheck_upper", "diurnalcheck_numsd"]:
            if ("[" in value) and ("]" in value) and ("*" in value):
                # old style of [value]*12
                value = value[value.index("[")+1:value.index("]")]
            elif ("[" in value) and ("]" in value) and ("*" not in value):
                # old style of [1,2,3,4,5,6,7,8,9,10,11,12]
                value = value.replace("[", "").replace("]", "")
            strip_list = [" ", '"', "'"]
        elif ("ExcludeDates" in attr or
              "ExcludeHours" in attr or
              "LowerCheck" in attr or
              "UpperCheck" in attr):
            strip_list = ["[", "]", '"', "'"]
        else:
            strip_list = ['"', "'"]
        for c in strip_list:
            if c in value:
                value = value.replace(c, "")
        attributes[attr] = value
    return attributes
