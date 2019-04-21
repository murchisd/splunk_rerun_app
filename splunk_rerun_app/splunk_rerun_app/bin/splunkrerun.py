#!/usr/bin/env python
#
# SplunkRerun
#
# Author:  Donald Murchison
# Version: 1.0
# 
# Purpose: Automatically rerun scheduled searches in Splunk for a specified "outage" period
#           
#          The rerun command will find searches by matching title to user specified regex. The command will
#          use the search's cron schedule to find times the search would have ran during the "outage" period.
#          It will earliest and latest to the scheduled run time to imitate as if splunk was actually running 
#          the search at that time. The command can trigger any actions for the search.
#
#          For Example:
#          "TEST-0001-test search" is scheduled to run everyday at 04:00 and look over the previous days logs 
#          If the rerun command was run with an outage period of 01/01/2019 - 01/03/2019. The "TEST-0001-test search" 
#          would be run for the scheduled time of 01/01/2019 04:00 with earliest 12/31/2018 00:00 and latest 01/01/2019 00:00
#          and the scheduled time of 01/02/2019 04:00 with earliest 01/01/2019 00:00 and latest 01/02/2019 00:00.
#          
# Usage:
#          | rerun regex="<Regex for Saved Search Titles>" trigger=<Boolean>
#
#          | rerun regex="TEST-00[0-9]{2}" trigger=t
#

import sys, time, re, datetime, tzlocal
from splunklib.searchcommands import dispatch, GeneratingCommand, Configuration, Option, validators, splunklib_logger as logger
import splunklib.client as client
import splunklib.results as results
from crontab import CronTab
from dateutil.relativedelta import relativedelta


@Configuration(streaming=False,type='reporting')
class SplunkRerunCommand(GeneratingCommand):

    regex = Option(require=True, validate=validators.RegularExpression(),
                    doc='''
                    **Syntax:** **regex=***<regex pattern>*
                    **Description:** regex pattern matching alerts/reports to rerun''')
    trigger = Option(validate=validators.Boolean(), default=False)

    #Todo - Update tz and epoch to be class veriables
    
    
    # Apply snap to earliest or latest
    # This would be the @<snap> period of pattern
    def applySnap(self, unit, original):
        tz = tzlocal.get_localzone()
        #Get epoch as Datetime based on timezone
        epoch = datetime.datetime.fromtimestamp(0,tz=tz)
        #Get runtime as Datetime based on timezone
        orig = datetime.datetime.fromtimestamp(int(original),tz=tz)
        #Depending on Snap replace units with 0 in Datetime
        #then convert back to epoch by subtracting epoch Datetime 
        #and returning difference in seconds 
        if(unit==None):
            return original
        if(unit=="m" or "min" in unit):
            x = (orig.replace(second=0)-epoch).total_seconds()
        elif(unit=="h" or "hr" in unit or "hour" in unit):
            x = (orig.replace(minute=0,second=0)-epoch).total_seconds()
        elif(unit=="d" or  "day" in unit):
            x = (orig.replace(hour=0,minute=0,second=0)-epoch).total_seconds()
        elif("mon" in unit):
            x = (orig.replace(day=1,hour=0,minute=0,second=0)-epoch).total_seconds()
        elif(unit=="y" or "yr" in unit or "year" in unit):
            x = (orig.replace(month=1,day=1,hour=0,minute=0,second=0)-epoch).total_seconds()
        elif("w" in unit):
            day = orig.weekday()
            x = ((orig-datetime.timedelta(days=day))-epoch).total_seconds()
        else:
            raise Exception("Error parsing snap unit; no match for unit")
        return x

    # Apply the offset to earliest and latest
    # This can be in 3 places in the pattern
    # <offset 1><offset 2>@<snap><snap offset>
    # -15m+5s@d+1h
    # function handles one offset at a time and does not matter which offset it is
    def applyOffset(self, offset, unit, original):
        # No need to convert to datetime in this function (exception month)
        # Just add or subtract the appropriate number of seconds
        if(offset==None or unit==None):
            return original
        if(unit=="s" or "sec" in unit):
            x = original + int(offset)
        elif(unit=="m" or "min" in unit):
            x = original + int(offset)*60
        elif(unit=="h" or "hr" in unit or "hour" in unit):
            x = original + int(offset)*60*60
        elif(unit=="d" or "day" in unit):
            x = original + int(offset)*60*60*24
        elif("w" in unit):
            x = original + int(offset)*60*60*24*7
        elif(unit=="y" or "yr" in unit or "year" in unit):
            x = original + int(offset)*60*60*24*7*365
        # Month is a special use case, since it is the only period that does not have a set number of seconds
        # To handle Month I convert to Datetime, and use relativedelta to add or subtract the number of months
        # then subtract epoch Datetime and get difference in seconds similar to applySnap
        elif("mon" in unit):
            try:
                tz = tzlocal.get_localzone()
                epoch = datetime.datetime.fromtimestamp(0,tz=tz)
                x = ((datetime.datetime.utcfromtimestamp(int(original),tz=tz)+relativedelta(months=int(offset)))-epoch).total_seconds()
            except NameError:
                raise Exception("No Month Functionality; install python-dateutil library")
            except Exception as e:
                raise e
        else:
            raise Exception("Error applying time offset; no match for unit")
        return x

    # Todo - better name for function; test more edge cases for possible earliest and latest patterns
    # getTimeRange will get earliest or latest based on the scheduled run time
    # relTime is the pattern for earliest or latest stored in Splunk
    # This could be as simple as -15m or @d or be complex as -1mon@y+12d
    def getTimeRange(self,relTime,runTime):
        #Regex to extract each offset and snap
        m = re.match("((?P<offset1>[+-]?\d+)(?P<unit1>[a-zA-Z]+)(?:(?P<offset2>[+-]\d+)(?P<unit2>[a-zA-Z]+))?)?(?:@(?P<snap>[a-zA-Z]+)(?:(?P<snapOff>[+-]\d+)(?P<snapUnit>[a-zA-Z]+))?)?",relTime)
        if relTime.isdigit():
            #If it is static time
            return relTime
        elif m and relTime!="now":
           #Apply snap then offsets in the following order: snap offset, first offset, second offset
           #The only time I think the order of offset would matter is when "mon" is used.
           self.logger.debug("[RERUN CMD]: Original: {0} {1}".format(runTime,relTime))
           runTime = self.applySnap(m.group('snap'),runTime)
           runTime = self.applyOffset(m.group('snapOff'),m.group('snapUnit'),runTime)
           runTime = self.applyOffset(m.group('offset1'),m.group('unit1'),runTime)
           runTime = self.applyOffset(m.group('offset2'),m.group('unit2'),runTime)
           self.logger.debug("[RERUN CMD]: Result: {}".format(runTime))
        return runTime
 
    def generate(self):
        #Todo - allow host to be set as paramater
        host = "localhost"
        #Get port info from uri in case using non-stnadard mgmt port
        splunkd_uri = self._metadata.searchinfo.splunkd_uri
        port = splunkd_uri.split(":")[-1]
        
        #Owner will be set as who ever ran the search
        owner = self._metadata.searchinfo.owner
        app= self._metadata.searchinfo.app
        
        #Get token to authenticate to API to rerun searches
        token=self._metadata.searchinfo.session_key
        
        #Use rerun command earliest and latest as the outage period, this way can be set by time picker instead of as parameters
        outageStart = self._metadata.searchinfo.earliest_time
        outageEnd = self._metadata.searchinfo.latest_time
        
        # Get the rerun command search id - this is because Splunk was not killing the python script when search was cancelled
        # Use this to monitor the status of the search and if it is no longer "Running" exit the script
        rerunSid = self._metadata.searchinfo.sid
        
        #Compile regex to find searches
        filter = re.compile(self.regex)
        
        #Try to connect to Splunk API
        self.logger.info("[RERUN CMD]: Connecting to Splunk API...")
        try:
            #service = client.connect(host=host, port=port, token=token, owner=owner, app=app)
            service = client.connect(host=host, port=port, token=token)
            self.logger.info("[RERUN CMD]: Connected to Splunk API successfully")
        except Exception as e:
            self.logger.error("[RERUN CMD]: {}".format(e.msg))
            
        #Splunk not stopping script going to ping sid from here and stop script if cancelled by user
        #Todo - look in to getting specific job info based on sid instead of use for statement
        for job in service.jobs:
            if job.sid == rerunSid:
                rerunJob = job
                self.logger.debug(job.state)        
        #If for some reason script cant find the search that triggered it 
        if not rerunJob:
            self.logger.error("[RERUN CMD]: Rerun Job SID not found exiting...")
            sys.exit(1)
        
        # Main loop to find an rerun searches
        for search in service.saved_searches:
           # Does not rerun disabled searches
           if filter.search(search.name) and search.is_scheduled=="1" and search.disabled=="0":
                #Parse the Splunk cron schedule for the found search
                ct = CronTab(search['content']['cron_schedule'])
                
                #Get earliest and latest pattern for search
                dispatch_earliest = search['content']['dispatch.earliest_time']
                dispatch_latest = search['content']['dispatch.latest_time']
                
                # Start with runTime equal to outageStart, crontab will be used to set this to the next time scheduled search
                # would have ran before rerunning 
                runTime=outageStart
                while True:
                    # Check to see if the search has been cancelled by user
                    rerunJob.refresh()
                    if rerunJob.state.content.dispatchState!="RUNNING":
                        sys.exit()
                    
                    # Get next scheduled run time, and break if greater than outageEnd
                    runTime = runTime + ct.next(now=runTime,default_utc=False)
                    if runTime > outageEnd or rerunJob.state.content.dispatchState!="RUNNING":
                        self.logger.error(rerunJob.state.content.dispatchState)
                        break
                    
                    #Get new earliest and latest based on new search run time
                    earliest = self.getTimeRange(dispatch_earliest,runTime)
                    latest = self.getTimeRange(dispatch_latest,runTime)
                    
                    # Set search parameters and run search
                    kwargs_block = {'dispatch.earliest_time':earliest, "dispatch.latest_time":latest, "trigger_actions":self.trigger}
                    job = search.dispatch(**kwargs_block)
                    time.sleep(0.25)
                    #Couldn't pass blocking argument, so sleep until isDone
                    while job['isDone']!="1":
                        self.logger.debug("[RERUN CMD]: Percent {}".format(job['doneProgress']))
                        time.sleep(1)
                        job.refresh()
                    message = "{} ran sucessfully for scheduled time {}".format(search.name,runTime)
                    self.logger.info("[RERUN CMD]: {}".format(message))
                    #Return results
                    yield {"_time":time.time(), "Message":message,"Search":search.name, "MissedRunTime":runTime, "MissedEarliest":earliest,"MissedLatest":latest, "TriggerActions":self.trigger,"Finished":job['isDone'],"CompletionPercentage":float(job['doneProgress'])*100,"ScanCount":job['scanCount'],"EventCount":job['eventCount'],"ResultCount": job['resultCount']}
                    
dispatch(SplunkRerunCommand, sys.argv, sys.stdin, sys.stdout, __name__)
