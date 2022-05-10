# standard modules
import calendar
import datetime
import logging
import os
# 3rd party modules
from scipy.interpolate import griddata
import numpy
import xlwt
# PFP modules
from scripts import constants as c
from scripts import pfp_io
from scripts import pfp_ts
from scripts import pfp_utils

logger = logging.getLogger("pfp_log")

def do_2dinterpolation(array_2d, tile="no", method="linear"):
    """
    Takes a 2d array as input and;
     1) tiles this into a 3 x 3 space (9 repeats of the original 2d array in 3 columns and 3 rows)
     2) removes the missing data (c.missing_value) from the tiled array
     3) does a bi-linear interpolation to replace the the missing data
     4) returns the central tile
     The effect is to replace missing data in the original 2d array with data from a bi-linear
     interpolation, the tiling repeats the original array along its boundaries to avoid problems
     at the array edges.
     Ian McHugh's cleaned up version (avoids error messages from matplotlib version of griddata).
     Checked by comparing the Fci(day) values from the original code and from this version.  The
     values were the same so this version pushed to GitHub on 11/5/2015.
    """
    WasMA = False
    if numpy.ma.isMA(array_2d):
        WasMA = True
        array_2d = numpy.ma.filled(array_2d, float(c.missing_value))
    if tile.lower() == "yes":
        # Tile the 2d array into a 3 by 3 array
        array_2d = numpy.tile(array_2d, (3, 3))
    # Get the dimensions of the tiled array and create coordinates and grid
    num_x = numpy.shape(array_2d)[1]
    array_x = numpy.arange(0, num_x)
    num_y = numpy.shape(array_2d)[0]
    array_y = numpy.arange(0, num_y)
    coords_x, coords_y = numpy.meshgrid(array_x, array_y)
    # Make a flat array of the tiled data
    data_1d = array_2d.flatten()
    # Make a 2d array of the coordinates
    data_coords = numpy.column_stack([coords_x.flatten(), coords_y.flatten()])
    # Define an index that will return all valid data for the array
    index = numpy.where(data_1d != c.missing_value)
    # Do the interpolation
    grid_z = griddata(data_coords[index], data_1d[index], (coords_x, coords_y), method = 'linear')
    if tile.lower() == "yes":
        # Retrieve the central tile
        array_2d_filled = grid_z[num_y // 3: num_y // 3 * 2, num_x // 3: num_x // 3 * 2]
    else:
        array_2d_filled = grid_z
    # Check something...
    if WasMA:
        array_2d_filled = numpy.ma.masked_values(array_2d_filled, c.missing_value)
        array_2d_filled = numpy.ma.masked_invalid(array_2d_filled)
    # Return the filled array
    return array_2d_filled

def write_data_1columnpermonth(xlSheet, data, ts, format_string=''):
    xlCol = 0
    # write the data to the xl file
    nrows = numpy.shape(data)[0]
    ncols = numpy.shape(data)[1]
    xlSheet.write(1,xlCol,'Hour')
    for j in range(nrows+1):
        xlSheet.write(j+2,xlCol,float(j)*ts/60)
    xlCol = xlCol + 1
    if len(format_string)!=0:
        d_xf = xlwt.easyxf(num_format_str=format_string)
    else:
        d_xf = xlwt.easyxf()
    for m in range(1,ncols+1):
        xlSheet.write(0,xlCol,calendar.month_abbr[m])
        xlSheet.write(1,xlCol,'Av')
        for j in range(nrows):
            xlSheet.write(j+2,xlCol,data[j,m-1],d_xf)
        xlCol = xlCol + 1

def write_data_1columnpertimestep(xlSheet, data, ts, startdate=None, format_string=''):
    tmp = data.copy()
    if numpy.ma.isMA(tmp): tmp = numpy.ma.filled(tmp,float(c.missing_value))
    xlCol = 0
    # write the data to the xl file
    xlSheet.write(1,xlCol,'Day')
    nrows = numpy.shape(tmp)[0]
    ncols = numpy.shape(tmp)[1]
    if startdate is None:
        for j in range(nrows+1):
            xlSheet.write(j+2,xlCol,j)
    else:
        d_xf = xlwt.easyxf(num_format_str='dd/mm/yyyy')
        for j in range(nrows):
            d = startdate + datetime.timedelta(days=j)
            xlSheet.write(j+2,xlCol,d,d_xf)
    xlCol = xlCol + 1
    if len(format_string)!=0:
        d_xf = xlwt.easyxf(num_format_str=format_string)
    else:
        d_xf = xlwt.easyxf()
    for m in range(1,ncols+1):
        xlSheet.write(1,xlCol,float(m)*ts/60)
        for j in range(nrows):
            xlSheet.write(j+2,xlCol,float(tmp[j,m-1]),d_xf)
        xlCol = xlCol + 1

def do_diurnalstats(Month, Hdh, data, xlSheet, format_string='',ts=30):
    xlCol = 0
    nInts = 24*int((60/ts)+0.5)
    Av_all = numpy.ma.zeros([nInts,12]) + float(c.missing_value)
    if len(format_string)!=0:
        d_xf = xlwt.easyxf(num_format_str=format_string)
    else:
        d_xf = xlwt.easyxf()
    for m in range(1,13):
        mi = numpy.where(Month==m)[0]
        Num,Hr,Av,Sd,Mx,Mn = get_diurnalstats(Hdh[mi],data[mi],ts)
        Av_all[:,m-1] = Av[:]
        Num = numpy.ma.filled(Num,float(c.missing_value))
        Hr = numpy.ma.filled(Hr,float(c.missing_value))
        Av = numpy.ma.filled(Av,float(c.missing_value))
        Sd = numpy.ma.filled(Sd,float(c.missing_value))
        Mx = numpy.ma.filled(Mx,float(c.missing_value))
        Mn = numpy.ma.filled(Mn,float(c.missing_value))
        if m==1:
            xlSheet.write(1,xlCol,'Hour')
            for j in range(len(Hr)):
                xlSheet.write(j+2,xlCol,Hr[j])
            xlCol = xlCol + 1
        xlSheet.write(0,xlCol,calendar.month_abbr[m])
        xlSheet.write(1,xlCol,'Num')
        xlSheet.write(1,xlCol+1,'Av')
        xlSheet.write(1,xlCol+2,'Sd')
        xlSheet.write(1,xlCol+3,'Mx')
        xlSheet.write(1,xlCol+4,'Mn')
        for j in range(len(Hr)):
            xlSheet.write(j+2,xlCol,int(Num[j]))
            xlSheet.write(j+2,xlCol+1,Av[j],d_xf)
            xlSheet.write(j+2,xlCol+2,Sd[j],d_xf)
            xlSheet.write(j+2,xlCol+3,Mx[j],d_xf)
            xlSheet.write(j+2,xlCol+4,Mn[j],d_xf)
        xlCol = xlCol + 5
    return Av_all

def get_diurnalstats(DecHour,Data,ts):
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

def get_rangecheck_limit(cf,label,upr_def=1E10,lwr_def=-1E10):
    upper = float(upr_def)
    lower = float(lwr_def)
    for section in ['Variables']:
        if label in list(cf[section].keys()):
            if 'RangeCheck' in list(cf[section][label].keys()):
                upper = float(cf[section][label]['RangeCheck']['upper'])
                lower = float(cf[section][label]['RangeCheck']['lower'])
    return upper,lower

def get_formatstring(cf,label,fmt_def=''):
    fmt_str = fmt_def
    for section in ['Variables']:
        if label in list(cf[section].keys()):
            if 'format' in list(cf[section][label].keys()):
                fmt_str = str(cf[section][label]['format'])
    return fmt_str

def climatology(cf):
    nc_filename = pfp_io.get_infilenamefromcf(cf)
    if not pfp_utils.file_exists(nc_filename):
        msg = " Unable to find netCDF file " + nc_filename
        logger.error(msg)
        return
    xl_filename = nc_filename.replace(".nc","_Climatology.xls")
    xlFile = xlwt.Workbook()
    ds = pfp_io.NetCDFRead(nc_filename)
    if ds.returncodes["value"] != 0: return
    # calculate Fa if it is not in the data structure
    if "Fa" not in list(ds.series.keys()):
        if "Fn" in list(ds.series.keys()) and "Fg" in list(ds.series.keys()):
            pfp_ts.CalculateAvailableEnergy(ds,Fa_out='Fa',Fn_in='Fn',Fg_in='Fg')
        else:
            logger.warning(" Fn or Fg not in data struicture")
    # get the time step
    ts = int(ds.globalattributes['time_step'])
    # get the datetime series
    dt = ds.series['DateTime']['Data']
    Hdh = numpy.array([(d.hour + d.minute/float(60)) for d in dt])
    Month = numpy.array([d.month for d in dt])
    # get the initial start and end dates
    StartDate = str(dt[0])
    EndDate = str(dt[-1])
    # find the start index of the first whole day (time=00:30)
    si = pfp_utils.GetDateIndex(dt,StartDate,ts=ts,default=0,match='startnextday')
    # find the end index of the last whole day (time=00:00)
    ei = pfp_utils.GetDateIndex(dt,EndDate,ts=ts,default=-1,match='endpreviousday')
    # get local views of the datetime series
    ldt = dt[si:ei+1]
    Hdh = Hdh[si:ei+1]
    Month = Month[si:ei+1]
    # get the number of time steps in a day and the number of days in the data
    ntsInDay = int(24.0*60.0/float(ts))
    nDays = int(len(ldt))//ntsInDay
    # loop over the variables listed in the control file
    for ThisOne in list(cf['Variables'].keys()):
        # check to see if an alternative variable name is given
        if "AltVarName" in list(cf['Variables'][ThisOne].keys()):
            # and get it if it was
            ThisOne = cf['Variables'][ThisOne]["AltVarName"]
        if ThisOne in list(ds.series.keys()):
            logger.info(" Doing climatology for "+ThisOne)
            data,f,a = pfp_utils.GetSeriesasMA(ds,ThisOne,si=si,ei=ei)
            if numpy.ma.count(data)==0:
                logger.warning(" No data for "+ThisOne+", skipping ...")
                continue
            fmt_str = get_formatstring(cf,ThisOne,fmt_def='')
            xlSheet = xlFile.add_sheet(ThisOne)
            Av_all = do_diurnalstats(Month,Hdh,data,xlSheet,format_string=fmt_str,ts=ts)
            # now do it for each day
            # we want to preserve any data that has been truncated by the use of the "startnextday"
            # and "endpreviousday" match options used above.  Here we revisit the start and end indices
            # and adjust these backwards and forwards respectively if data has been truncated.
            nDays_daily = nDays
            ei_daily = ei
            si_daily = si
            sdate = ldt[0]
            # is there data after the current end date?
            if dt[-1]>ldt[-1]:
                # if so, push the end index back by 1 day so it is included
                ei_daily = ei + ntsInDay
                nDays_daily = nDays_daily + 1
            # is there data before the current start date?
            if dt[0]<ldt[0]:
                # if so, push the start index back by 1 day so it is included
                si_daily = si - ntsInDay
                nDays_daily = nDays_daily + 1
                sdate = ldt[0]-datetime.timedelta(days=1)
            # get the data and use the "pad" option to add missing data if required to
            # complete the extra days
            data,f,a = pfp_utils.GetSeriesasMA(ds,ThisOne,si=si_daily,ei=ei_daily,mode="pad")
            ldt2,f,a = pfp_utils.GetSeriesasMA(ds,"DateTime",si=si_daily,ei=ei_daily,mode="pad")
            data_daily = data.reshape(nDays_daily, ntsInDay)
            xlSheet = xlFile.add_sheet(ThisOne+'(day)')
            write_data_1columnpertimestep(xlSheet, data_daily, ts, startdate=sdate, format_string=fmt_str)
            data_daily_i = do_2dinterpolation(data_daily)
            # check to see if the interpolation has left some data unfilled
            # this can happen if there is missing data at the boundaries of the date x hour
            # 2D array
            idx = numpy.where(numpy.ma.getmaskarray(data_daily_i) == True)
            # fill any missing data in the interpolated array with the monthly climatology
            month = numpy.array([dt.month-1 for dt in ldt2])
            month_daily = month.reshape(nDays_daily, ntsInDay)
            hour = numpy.array([int(2*(dt.hour+float(dt.minute)/float(60))) for dt in ldt2])
            hour_daily = hour.reshape(nDays_daily,ntsInDay)
            data_daily_i[idx] = Av_all[hour_daily[idx], month_daily[idx]]
            # write the interpolated data to the Excel workbook
            xlSheet = xlFile.add_sheet(ThisOne+'i(day)')
            write_data_1columnpertimestep(xlSheet, data_daily_i, ts, startdate=sdate, format_string=fmt_str)
        else:
            logger.warning(" Requested variable "+ThisOne+" not in data structure")
            continue
    logger.info(" Saving Excel file "+os.path.split(xl_filename)[1])
    xlFile.save(xl_filename)
    return
