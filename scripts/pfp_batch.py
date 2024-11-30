# standard modules
import datetime
import logging
import os
import sys
import traceback
# 3rd party modules
import dateutil
# PFP modules
from scripts import pfp_clim
from scripts import pfp_compliance
from scripts import pfp_cpd_barr
from scripts import pfp_cpd_mchugh
from scripts import pfp_cpd_mcnew
from scripts import pfp_io
from scripts import pfp_levels
from scripts import pfp_mpt
from scripts import pfp_parse
from scripts import pfp_plot
from scripts import pfp_utils

logger = logging.getLogger("pfp_log")

def do_batch_fingerprints(cfg):
    """
    Purpose:
     Plot fingerprints at the end of conatenation, L4 and L5.
    Author: PRI
    Date: Back in the day
    """
    cfg_fp_uri = os.path.join("controlfiles", "standard", "fingerprint.txt")
    cfg_fp = pfp_io.get_controlfilecontents(cfg_fp_uri)
    file_name = pfp_io.get_outfilenamefromcf(cfg)
    file_path = os.path.join(os.path.split(file_name)[0], "")
    plot_path = pfp_utils.get_keyvaluefromcf(cfg, ["Files"], "plot_path", default="plots/")
    cfg_fp["Files"] = {"file_path": file_path, "in_filename": os.path.split(file_name)[1],
                       "plot_path": plot_path}
    cfg_fp["Options"] = {"call_mode": "batch", "show_plots": "No"}
    msg = " Doing fingerprint plots using " + cfg_fp["Files"]["in_filename"]
    logger.info(msg)
    pfp_plot.plot_fingerprint(cfg_fp)
    logger.info("Finished fingerprint plots")
    return
def do_batch_stacked_timeseries(cfg, ds, start=0, end=-1):
    """
    Purpose:
     Plot stacked timeseries for the level being processed.
    Author: PRI
    Date: August 2024
    """
    msg = "Doing stacked timeseries plots"
    logger.info(msg)
    pfp_plot.plot_stacked_timeseries(cfg, ds, start=start, end=end)
    msg = "Finished stacked timeseries plots"
    logger.info(msg)
    return
def do_L1_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting L1 processing with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf_l1 = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.l1_update_controlfile(cf_l1):
                continue
            if "Options" not in cf_l1:
                cf_l1["Options"] = {}
            cf_l1["Options"]["call_mode"] = "batch"
            cf_l1["Options"]["show_plots"] = "No"
            if pfp_compliance.check_l1_controlfile(cf_l1):
                ds1 = pfp_levels.l1_read_input(cf_l1)
                outfilename = pfp_io.get_outfilenamefromcf(cf_l1)
                pfp_io.NetCDFWrite(outfilename, ds1)
                msg = "Finished L1 processing with " + cf_file_name[1]
                logger.info(msg)
                logger.info("")
            else:
                msg = "Error occurred checking compliance of L1 controlfile"
                logger.error(msg)
        except Exception:
            msg = "Error occurred during L1 processing " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_L2_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting L2 processing with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf_l2 = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.l2_update_controlfile(cf_l2):
                continue
            if "Options" not in cf_l2:
                cf_l2["Options"] = {}
            cf_l2["Options"]["call_mode"] = "batch"
            cf_l2["Options"]["show_plots"] = "No"
            infilename = pfp_io.get_infilenamefromcf(cf_l2)
            ds1 = pfp_io.NetCDFRead(infilename)
            if ds1.info["returncodes"]["value"] != 0:
                return
            pfp_compliance.check_l2_options(cf_l2, ds1)
            if ds1.info["returncodes"]["value"] != 0:
                return
            if pfp_compliance.check_l2_controlfile(cf_l2):
                ds2 = pfp_levels.l2_quality_control(cf_l2, ds1)
                outfilename = pfp_io.get_outfilenamefromcf(cf_l2)
                pfp_io.NetCDFWrite(outfilename, ds2)
                msg = "Finished L2 processing with " + cf_file_name[1]
                logger.info(msg)
                if "Plots" in list(cf_l2.keys()):
                    logger.info("Plotting L1 and L2 data")
                    for nFig in list(cf_l2['Plots'].keys()):
                        if "(disabled)" in nFig:
                            continue
                        plt_cf = cf_l2['Plots'][str(nFig)]
                        if 'type' in plt_cf.keys():
                            if str(plt_cf['type']).lower() == 'xy':
                                pfp_plot.plotxy(cf_l2, nFig, plt_cf, ds1, ds2)
                            else:
                                pfp_plot.plottimeseries(cf_l2, nFig, ds1, ds2)
                        else:
                            pfp_plot.plottimeseries(cf_l2, nFig, ds1, ds2)
                    logger.info("Finished plotting L1 and L2 data")
                logger.info("")
            else:
                msg = "Error occurred checking compliance of L2 controlfile"
                logger.error(msg)
        except Exception:
            msg = "Error occurred during L2 processing " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_L3_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting L3 processing with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf_l3 = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.l3_update_controlfile(cf_l3):
                continue
            if "Options" not in cf_l3:
                cf_l3["Options"] = {}
            cf_l3["Options"]["call_mode"] = "batch"
            cf_l3["Options"]["show_plots"] = "No"
            infilename = pfp_io.get_infilenamefromcf(cf_l3)
            ds2 = pfp_io.NetCDFRead(infilename)
            if ds2.info["returncodes"]["value"] != 0:
                return
            if not pfp_compliance.check_l3_controlfile(cf_l3):
                return
            ds3 = pfp_levels.l3_post_processing(cf_l3, ds2)
            outfilename = pfp_io.get_outfilenamefromcf(cf_l3)
            pfp_io.NetCDFWrite(outfilename, ds3)
            msg = "Finished L3 processing with " + cf_file_name[1]
            logger.info(msg)
            if "Plots" in list(cf_l3.keys()):
                logger.info("Plotting L3 data")
                for nFig in list(cf_l3['Plots'].keys()):
                    if "(disabled)" in nFig:
                        continue
                    plt_cf = cf_l3['Plots'][str(nFig)]
                    if 'type' in plt_cf.keys():
                        if str(plt_cf['type']).lower() == 'xy':
                            pfp_plot.plotxy(cf_l3, nFig, plt_cf, ds2, ds3)
                        else:
                            pfp_plot.plottimeseries(cf_l3, nFig, ds2, ds3)
                    else:
                        pfp_plot.plottimeseries(cf_l3, nFig, ds2, ds3)
                logger.info("Finished plotting L3 data")
            # plot the L3 fingerprints
            logger.info("Plotting L3 fingerprints")
            do_batch_fingerprints(cf_l3)
            logger.info("Finished L3 fingerprints")
            # do the stacked time series plots
            ldt = pfp_utils.GetVariable(ds3, "DateTime")
            end = ldt["Data"][-1]
            start = end - dateutil.relativedelta.relativedelta(months=1)
            radn_labels = ["Fsd", "Fsu", "Fld", "Flu", "Fn"]
            flux_labels = ["Fh", "Fe", "Fco2", "Fm"]
            met_labels = ["Precip", "Ta", "RH", "Ws", "Wd", "ps"]
            soil_labels = ["Ts", "Fg", "Sws"]
            plot_labels = radn_labels + flux_labels + met_labels + soil_labels
            cf_l3["Options"]["plot_stacked_timeseries"] = {"plot_labels": plot_labels,
                                                           "start": start, "end": end,}
            do_batch_stacked_timeseries(cf_l3, ds3, start=start, end=end)
            logger.info("")
        except Exception:
            msg = "Error occurred during L3 processing " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_ecostress_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting ECOSTRESS output with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf = pfp_io.get_controlfilecontents(cf_level[i])
            pfp_io.write_csv_ecostress(cf)
            msg = "Finished ECOSTRESS output with " + cf_file_name[1]
            logger.info(msg)
            logger.info("")
        except Exception:
            msg = "Error occurred during ECOSTRESS output with " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_fluxnet_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting FluxNet output with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        cf = pfp_io.get_controlfilecontents(cf_level[i])
        pfp_io.write_csv_fluxnet(cf)
        msg = "Finished FluxNet output with " + cf_file_name[1]
        logger.info(msg)
        logger.info("")
    return 1
def do_reddyproc_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting REddyProc output with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        cf = pfp_io.get_controlfilecontents(cf_level[i])
        pfp_io.write_tsv_reddyproc(cf)
        msg = "Finished REddyProc output with " + cf_file_name[1]
        logger.info(msg)
        logger.info("")
    return 1
def do_concatenate_batch(main_ui, cf_level):
    sites = sorted(list(cf_level.keys()), key=int)
    for i in sites:
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting concatenation with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf_cc = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.concatenate_update_controlfile(cf_cc):
                continue
            info = pfp_parse.ParseConcatenateControlFile(cf_cc)
            if not info["NetCDFConcatenate"]["OK"]:
                msg = " Error occurred parsing the control file " + cf_file_name[1]
                logger.error(msg)
                continue
            pfp_io.NetCDFConcatenate(info)
            msg = "Finished concatenation with " + cf_file_name[1]
            logger.info(msg)
            # do the CF compliance check
            #do_batch_cfcheck(cf_cc)
            # and then plot the fingerprints for the concatenated files
            do_batch_fingerprints(cf_cc)
            logger.info("")
        except Exception:
            msg = "Error occurred during concatenation with " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_climatology_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting climatology with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf_ct = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.climatology_update_controlfile(cf_ct):
                continue
            pfp_clim.climatology(cf_ct)
            msg = "Finished climatology with " + cf_file_name[1]
            logger.info(msg)
            logger.info("")
        except Exception:
            msg = "Error occurred during climatology with " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_cpd_barr_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting CPD (Barr) with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.cpd_barr_update_controlfile(cf):
                continue
            if "Options" not in cf:
                cf["Options"] = {}
            cf["Options"]["call_mode"] = "batch"
            cf["Options"]["show_plots"] = "No"
            pfp_cpd_barr.cpd_barr_main(cf)
            msg = "Finished CPD (Barr) with " + cf_file_name[1]
            logger.info(msg)
            logger.info("")
        except Exception:
            msg = "Error occurred during CPD (Barr) with " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_cpd_mchugh_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting CPD (McHugh) with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.cpd_mchugh_update_controlfile(cf):
                continue
            if "Options" not in cf:
                cf["Options"] = {}
            cf["Options"]["call_mode"] = "batch"
            cf["Options"]["show_plots"] = "No"
            pfp_cpd_mchugh.cpd_mchugh_main(cf)
            msg = "Finished CPD (McHugh) with " + cf_file_name[1]
            logger.info(msg)
            logger.info("")
        except Exception:
            msg = "Error occurred during CPD (McHugh) with " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_cpd_mcnew_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting CPD (McNew) with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.cpd_mcnew_update_controlfile(cf):
                continue
            if "Options" not in cf:
                cf["Options"] = {}
            cf["Options"]["call_mode"] = "batch"
            cf["Options"]["show_plots"] = "No"
            pfp_cpd_mcnew.cpd_mcnew_main(cf)
            msg = "Finished CPD (McNew) with " + cf_file_name[1]
            logger.info(msg)
            logger.info("")
        except Exception:
            msg = "Error occurred during CPD (McNew) with " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_mpt_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting MPT with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.mpt_update_controlfile(cf):
                continue
            if "Options" not in cf:
                cf["Options"] = {}
            cf["Options"]["call_mode"] = "batch"
            cf["Options"]["show_plots"] = "No"
            pfp_mpt.mpt_main(cf)
            msg = "Finished MPT with " + cf_file_name[1]
            logger.info(msg)
            logger.info("")
        except Exception:
            msg = "Error occurred during MPT with " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_L4_batch(main_ui, cf_level):
    sites = sorted(list(cf_level.keys()), key=int)
    for i in sites:
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting L4 processing with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf_l4 = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.l4_update_controlfile(cf_l4):
                continue
            if "Options" not in cf_l4:
                cf_l4["Options"] = {}
            cf_l4["Options"]["call_mode"] = "batch"
            cf_l4["Options"]["show_plots"] = "No"
            infilename = pfp_io.get_infilenamefromcf(cf_l4)
            ds3 = pfp_io.NetCDFRead(infilename)
            if ds3.info["returncodes"]["value"] != 0: return
            ds4 = pfp_levels.l4_gapfill_drivers(None, cf_l4, ds3)
            outfilename = pfp_io.get_outfilenamefromcf(cf_l4)
            pfp_io.NetCDFWrite(outfilename, ds4)
            msg = "Finished L4 processing with " + cf_file_name[1]
            logger.info(msg)
            # do the CF compliance check
            #do_batch_cfcheck(cf_l4)
            # plot the L4 fingerprints
            do_batch_fingerprints(cf_l4)
            logger.info("")
        except Exception:
            msg = "Error occurred during L4 with " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_L5_batch(main_ui, cf_level):
    sites = sorted(list(cf_level.keys()), key=int)
    for i in sites:
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting L5 processing with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf_l5 = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.l5_update_controlfile(cf_l5):
                continue
            if "Options" not in cf_l5:
                cf_l5["Options"] = {}
            cf_l5["Options"]["call_mode"] = "batch"
            cf_l5["Options"]["show_plots"] = "No"
            infilename = pfp_io.get_infilenamefromcf(cf_l5)
            ds4 = pfp_io.NetCDFRead(infilename)
            if ds4.info["returncodes"]["value"] != 0:
                return
            if pfp_compliance.check_l5_controlfile(cf_l5):
                ds5 = pfp_levels.l5_gapfill_fluxes(None, cf_l5, ds4)
                outfilename = pfp_io.get_outfilenamefromcf(cf_l5)
                pfp_io.NetCDFWrite(outfilename, ds5)
                msg = "Finished L5 processing with " + cf_file_name[1]
                logger.info(msg)
                # do the CF compliance check
                #do_batch_cfcheck(cf_l5)
                # plot the L5 fingerprints
                do_batch_fingerprints(cf_l5)
                logger.info("")
            else:
                msg = "Error occurred checking compliance of L5 controlfile"
                logger.error(msg)
        except Exception:
            msg = "Error occurred during L5 with " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_L6_batch(main_ui, cf_level):
    for i in list(cf_level.keys()):
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        cf_file_name = os.path.split(cf_level[i])
        msg = "Starting L6 processing with " + cf_file_name[1]
        logger.info(msg)
        if not check_file_exits(cf_level[i]):
            return 0
        try:
            cf_l6 = pfp_io.get_controlfilecontents(cf_level[i])
            if not pfp_compliance.l6_update_controlfile(cf_l6):
                continue
            if "Options" not in cf_l6:
                cf_l6["Options"] = {}
            cf_l6["Options"]["call_mode"] = "batch"
            cf_l6["Options"]["show_plots"] = "No"
            infilename = pfp_io.get_infilenamefromcf(cf_l6)
            ds5 = pfp_io.NetCDFRead(infilename)
            if ds5.info["returncodes"]["value"] != 0:
                return
            if pfp_compliance.check_l6_controlfile(cf_l6):
                ds6 = pfp_levels.l6_partition(None, cf_l6, ds5)
                outfilename = pfp_io.get_outfilenamefromcf(cf_l6)
                pfp_io.NetCDFWrite(outfilename, ds6)
                msg = "Finished L6 processing with " + cf_file_name[1]
                logger.info(msg)
                # do the CF compliance check
                #do_batch_cfcheck(cf_l6)
                logger.info("")
            else:
                msg = "Error occurred checking compliance of L6 controlfile"
                logger.error(msg)
        except Exception:
            msg = "Error occurred during L6 with " + cf_file_name[1]
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            continue
    return 1
def do_levels_batch(main_ui):
    logger = logging.getLogger("pfp_log")
    if main_ui.mode == "interactive":
        tab_index_running = main_ui.tabs.tab_index_running
        cf_batch = main_ui.tabs.tab_dict[tab_index_running].get_data_from_model()
    elif main_ui.mode == "batch":
        cf_batch = main_ui.cfg
    else:
        msg = "Unrecognised option for mode (" + main_ui.mode + ")"
        logger.error(msg)
        raise RuntimeError
    start = datetime.datetime.now()
    msg = "Started batch processing at " + start.strftime("%Y%m%d%H%M")
    logger.info(msg)
    if "Options" in cf_batch:
        if "levels" in cf_batch["Options"]:
            levels = pfp_utils.string_to_list(cf_batch["Options"]["levels"])
        else:
            msg = "No 'levels' entry found in [Options] section"
            logger.error(msg)
            sys.exit()
    else:
        msg = "No [Options] section in control file"
        logger.error(msg)
        sys.exit()
    processing_levels = ["l1", "l2", "l3",
                         "ecostress", "fluxnet", "reddyproc",
                         "concatenate", "climatology",
                         "cpd_barr", "cpd_mchugh", "cpd_mcnew", "mpt",
                         "l4", "l5", "l6"]
    for level in levels:
        # check the stop flag
        if main_ui.stop_flag:
            # break out of the loop if user requested stop
            break
        if level.lower() not in processing_levels:
            msg = "Unrecognised level " + level
            logger.warning(msg)
            continue
        if level.lower() == "l1":
            # L1 processing
            if not do_L1_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "l2":
            # L2 processing
            if not do_L2_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "l3":
            # L3 processing
            if not do_L3_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "ecostress":
            # convert netCDF files to ECOSTRESS CSV files
            if not do_ecostress_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "fluxnet":
            # convert netCDF files to FluxNet CSV files
            if not do_fluxnet_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "reddyproc":
            # convert netCDF files to REddyProc CSV files
            if not do_reddyproc_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "concatenate":
            # concatenate netCDF files
            if not do_concatenate_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "climatology":
            # climatology
            if not do_climatology_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "cpd_barr":
            # ustar threshold from change point detection
            if not do_cpd_barr_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "cpd_mchugh":
            # ustar threshold from change point detection
            if not do_cpd_mchugh_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "cpd_mcnew":
            # ustar threshold from change point detection
            if not do_cpd_mcnew_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "mpt":
            # ustar threshold from change point detection
            if not do_mpt_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "l4":
            # L4 processing
            if not do_L4_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "l5":
            # L5 processing
            if not do_L5_batch(main_ui, cf_batch["Levels"][level]):
                break
        elif level.lower() == "l6":
            # L6 processing
            if not do_L6_batch(main_ui, cf_batch["Levels"][level]):
                break
    end = datetime.datetime.now()
    msg = " Finished batch processing at " + end.strftime("%Y%m%d%H%M")
    logger.info(msg)
    return
def check_file_exits(file_name):
    if not os.path.isfile(file_name):
        msg = file_name + " not found."
        logger.error("")
        logger.error(msg)
        logger.error("")
        ok = 0
    else:
        ok = 1
    return ok
