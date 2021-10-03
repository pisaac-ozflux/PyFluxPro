# standard Python modules
import datetime
import logging
import os
import subprocess
# 3rd party
import numpy
import pandas
# PFP modules
from scripts import pfp_io
from scripts import pfp_utils

logger = logging.getLogger("pfp_log")

def get_seasonal_results(contents):
    # get the seasonal values
    season_values = numpy.array([float(s) for s in contents[2].split()])
    season_counts = numpy.array([int(s) for s in contents[3].split()])
    return {"value": season_values, "count": season_counts}

def get_annual_results(contents):
    # get the annual values
    season_values = numpy.array([float(s) for s in contents[2].split()])
    season_counts = numpy.array([int(s) for s in contents[3].split()])
    annual_values = numpy.max(season_values)
    annual_counts = numpy.sum(season_counts)
    return {"value": annual_values, "count": annual_counts}

def get_temperature_class_results(contents):
    # get the seasonal results by temperature class
    temperature_classes = {}
    for i, n in enumerate(range(7, 14)):
        temperature_classes[i] = {}
        temperature_classes[i]["values"] = numpy.array([float(s) for s in contents[n].split()])
        temperature_classes[i]["counts"] = numpy.zeros(len(temperature_classes[i]["values"]))
    return temperature_classes

def get_bootstrap_results(contents):
    # get the number of seasons
    season_values = numpy.array([float(s) for s in contents[2].split()])
    number_seasons = len(season_values)
    # get the individual bootstrap results
    bootstrap_results = {}
    for i in range(number_seasons):
        bootstrap_results[i] = {"values": [], "counts": []}
    # on Windows machines, len(contents[n]) == 1 for the first empty line after the bootstrap section
    n = 17
    while len(contents[n]) > 1:
        season_values = numpy.array([float(s) for s in contents[n][0:contents[n].index("forward")].split()])
        season_counts = numpy.array([int(s) for s in contents[n+1][0:].split()])
        for i in range(number_seasons):
            if i < len(season_values):
                bootstrap_results[i]["values"] = numpy.append(bootstrap_results[i]["values"], season_values[i])
                bootstrap_results[i]["counts"] = numpy.append(bootstrap_results[i]["counts"], season_counts[i])
            else:
                bootstrap_results[i]["values"] = numpy.append(bootstrap_results[i]["values"], float(-9999))
                bootstrap_results[i]["counts"] = numpy.append(bootstrap_results[i]["counts"], float(-9999))
        n = n + 2
    return bootstrap_results

def make_data_array(cf, ds, current_year):
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    nrecs = int(ds.globalattributes["nc_nrecs"])
    ts = int(float(ds.globalattributes["time_step"]))
    start = datetime.datetime(current_year, 1, 1, 0, 0, 0) + datetime.timedelta(minutes=ts)
    end = datetime.datetime(current_year+1, 1, 1, 0, 0, 0)
    cdt = numpy.array([dt for dt in pfp_utils.perdelta(start, end, datetime.timedelta(minutes=ts))])
    mt = numpy.ones(len(cdt))*float(-9999)
    mt_list = [cdt] + [mt for n in list(cf["Variables"].keys())]
    data = numpy.stack(mt_list, axis=-1)
    si = pfp_utils.GetDateIndex(ldt["Data"], start, default=0)
    ei = pfp_utils.GetDateIndex(ldt["Data"], end, default=nrecs)
    dt = pfp_utils.GetVariable(ds, "DateTime", start=si, end=ei)
    idx1, idx2 = pfp_utils.FindMatchingIndices(cdt, dt["Data"])
    for n, cf_label in enumerate(list(cf["Variables"].keys())):
        label = cf["Variables"][cf_label]["name"]
        var = pfp_utils.GetVariable(ds, label, start=si, end=ei)
        data[idx1,n+1] = var["Data"]
    # convert datetime to ISO dates
    data[:,0] = numpy.array([int(xdt.strftime("%Y%m%d%H%M")) for xdt in cdt])
    return data

def mpt_main(cf):
    base_file_path = cf["Files"]["file_path"]
    nc_file_name = cf["Files"]["in_filename"]
    nc_file_path = os.path.join(base_file_path, nc_file_name)
    ds = pfp_io.nc_read_series(nc_file_path)
    if ds.returncodes["value"] != 0: return
    out_file_paths = run_mpt_code(cf, ds, nc_file_name)
    if len(out_file_paths) == 0:
        return
    ustar_results = read_mpt_output(out_file_paths)
    mpt_file_path = nc_file_path.replace(".nc", "_MPT.xlsx")
    xl_write_mpt(mpt_file_path, ustar_results)
    return

def run_mpt_code(cf, ds, nc_file_name):
    """
    Purpose:
     Runs the MPT u* threshold detection code for each year in the data set.
    Usage:
    Side effects:
     Writes an ASCII file of results which is read by later code.
    Author: Alessio Ribeca wrote the C code
            PRI wrote this wrapper
    Date: Back in the day
    """
    # set up file paths, headers and formats etc
    out_file_paths = {}
    header = "TIMESTAMP,NEE,VPD,USTAR,TA,SW_IN,H,LE"
    # check that all variables listed in the header are defined in the control file
    labels = cf["Variables"].keys()
    for label in labels:
        if label not in header:
            msg = " MPT: variable " + label + " not defined in control file, skipping MPT ..."
            logger.error(msg)
            return out_file_paths
        else:
            msg = " MPT: Using variable " + cf["Variables"][label]["name"] + " for " + label
            logger.info(msg)
    fmt = "%12i,%f,%f,%f,%f,%f,%f,%f"
    log_file_path = os.path.join("mpt", "log", "mpt.log")
    mptlogfile = open(log_file_path, "w")
    in_base_path = os.path.join("mpt", "input", "")
    out_base_path = os.path.join("mpt", "output", "")
    # get the time step
    ts = int(float(ds.globalattributes["time_step"]))
    if (ts != 30) and (ts != 60):
        msg = "MPT: time step must be 30 or 60 minutes (" + str(ts) + "), skipping MPT ..."
        logger.error(msg)
        return out_file_paths
    # get the datetime
    dt = pfp_utils.GetVariable(ds, "DateTime")
    # subtract 1 time step to avoid orphan years
    cdt = dt["Data"] - datetime.timedelta(minutes=ts)
    # get a list of the years in the data set
    years = sorted(list(set([ldt.year for ldt in cdt])))
    # loop over years
    for year in years:
        msg = " MPT: processing year " + str(year)
        logger.info(msg)
        in_name = nc_file_name.replace(".nc","_"+str(year)+"_MPT.csv")
        in_full_path = os.path.join(in_base_path, in_name)
        out_full_path = in_full_path.replace("input", "output").replace(".csv", "_ut.txt")
        data = make_data_array(cf, ds, year)
        numpy.savetxt(in_full_path, data, header=header, delimiter=",", comments="", fmt=fmt)
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        ustar_mp_exe = os.path.join(base_path, "mpt", "bin", "ustar_mp")
        if ts == 30:
            cmd = [ustar_mp_exe, "-input_path="+in_full_path, "-output_path="+out_base_path]
        elif ts == 60:
            cmd = [ustar_mp_exe, "-input_path="+in_full_path, "-output_path="+out_base_path, "-hourly"]
        subprocess.call(cmd, stdout=mptlogfile)
        if os.path.isfile(out_full_path):
            out_file_paths[year] = out_full_path
    mptlogfile.close()
    return out_file_paths

def read_mpt_output(out_file_paths):
    ustar_results = {"Annual":{}, "Years":{}}
    ury = ustar_results["Years"]
    year_list = sorted(out_file_paths.keys())
    for year in year_list:
        ury[year] = {}
        out_file_path = out_file_paths[year]
        with open(out_file_path) as mpt_file:
            contents = [l.rstrip('\n') for l in mpt_file.readlines()]
        # check the first line to make sure it is what we expect
        if not "ustar threshold by season" in contents[0] or not "bootstrapping" in contents[15]:
            msg = "MPT: unexpected contents in MPT output file"
            logger.error(msg)
            return ustar_results
        ury[year]["seasonal"] = get_seasonal_results(contents)
        ury[year]["annual"] = get_annual_results(contents)
        ury[year]["temperature_classes"] = get_temperature_class_results(contents)
        ury[year]["bootstraps"] = get_bootstrap_results(contents)
    return ustar_results

def xl_write_mpt(mpt_full_path, ustar_results):
    """
    Purpose:
    Usage:
    Side effects:
    Author: PRI
    Date: November 2019
    Mods:
     September 2021 - rewritten to use pandas
    """
    annual = {}
    years = sorted(list(ustar_results["Years"].keys()))
    for year in years:
        season_list = sorted(list(ustar_results["Years"][year]["bootstraps"].keys()))
        values = ustar_results["Years"][year]["bootstraps"][0]["values"]
        season_list.remove(0)
        for s in season_list:
            values = numpy.concatenate((values, ustar_results["Years"][year]["bootstraps"][s]["values"]))
        values = numpy.ma.masked_values(values, -9999)
        ustar_results["Years"][year]["annual"]["stdev"] = numpy.ma.std(values)
        annual[year] = {"ustar_mean": ustar_results["Years"][year]["annual"]["value"],
                        "ustar_sig": ustar_results["Years"][year]["annual"]["stdev"]}
    xlwriter = pandas.ExcelWriter(mpt_full_path)
    df_annual = pandas.DataFrame.from_dict(annual, orient='index')
    df_annual.index.names = ["Year"]
    df_annual.to_excel(xlwriter, sheet_name='Annual')
    by_years = {}
    for year in years:
        by_years["Seasonal"] = {"Values": ustar_results["Years"][year]["seasonal"]["value"],
                                "Counts": ustar_results["Years"][year]["seasonal"]["count"]}
        by_years["Temperature classes"] = {}
        temperature_classes = sorted(list(ustar_results["Years"][year]["temperature_classes"].keys()))
        for t in temperature_classes:
            by_years["Temperature classes"][t] = {0: ustar_results["Years"][year]["temperature_classes"][t]["values"][0],
                                                  1: ustar_results["Years"][year]["temperature_classes"][t]["values"][1],
                                                  2: ustar_results["Years"][year]["temperature_classes"][t]["values"][2],
                                                  3: ustar_results["Years"][year]["temperature_classes"][t]["values"][3]}
        by_years["Bootstraps"] = {"0 Values": ustar_results["Years"][year]["bootstraps"][0]["values"],
                                  "0 Counts": ustar_results["Years"][year]["bootstraps"][0]["counts"],
                                  "1 Values": ustar_results["Years"][year]["bootstraps"][1]["values"],
                                  "1 Counts": ustar_results["Years"][year]["bootstraps"][1]["counts"],
                                  "2 Values": ustar_results["Years"][year]["bootstraps"][2]["values"],
                                  "2 Counts": ustar_results["Years"][year]["bootstraps"][2]["counts"],
                                  "3 Values": ustar_results["Years"][year]["bootstraps"][3]["values"],
                                  "3 Counts": ustar_results["Years"][year]["bootstraps"][3]["counts"]}
        df_seasonal = pandas.DataFrame.from_dict(by_years["Seasonal"])
        df_seasonal.index.names = ["Seasonal"]
        df_seasonal.to_excel(xlwriter, sheet_name=str(year), startrow=0)
        df_temperature = pandas.DataFrame.from_dict(by_years["Temperature classes"], orient='index')
        df_temperature.index.names = ["Temperature classes"]
        df_temperature.to_excel(xlwriter, sheet_name=str(year), startrow=10)
        df_bootstraps = pandas.DataFrame.from_dict(by_years["Bootstraps"])
        df_bootstraps.index.names = ["Bootstraps"]
        df_bootstraps.to_excel(xlwriter, sheet_name=str(year), startrow=20)
    xlwriter.save()
    return
