Splunk Rerun App
===============================

An application that implements a custom Splunk command, `rerun`, and a simple Dashboard to help with the command use. The custom command uses the Python SDK's `GeneratingCommand` to rerun saved searches through the Splunk API.

# Purpose

Rerun scheduled searches in Splunk for a specified "outage" period.
           
The rerun command will find searches by matching title to user specified regex. The command will use the search's cron schedule to find times the search would have ran during the "outage" period. It will set earliest and latest to the scheduled run time to emulate as if Splunk was actually running the search at the scheduled time. The command can also trigger any actions for the search.

For Example:
"TEST-0001-test search" is scheduled to run everyday at 04:00 with the Timerange of "Yesterday" (earliest=-1d@d latest=@d). If the rerun command was run with an outage period of 01/01/2019 - 01/03/2019, The "TEST-0001-test search" would be run for the scheduled time of 01/01/2019 04:00 with earliest 12/31/2018 00:00 and latest 01/01/2019 00:00 and the scheduled time of 01/02/2019 04:00 with earliest 01/01/2019 00:00 and latest 01/02/2019 00:00.

# Why?

This command was written to help recover from any Splunk issues that may have caused Alerts and Reports to not run or return incomplete or incorrect results.

Often when rerunning scheduled alerts or reports for the situations above it is not as easy as just opening in search and extending the time range. Reports may be getting statistics for specific time intervals and modifying the searches to account for this can become time consuming. Another problem with manually rerunning searches is many alerts and reports could have different trigger actions or results may be sent to different groups. The rerun command helps automatically handle the problems. 

Example Situations:

* Search Head goes down for an extended period  
* Corrupt Buckets were causing indexers to return incomplete results
* New historical data was added and would like to include data in past reports
          
# Pre-requisites.

* Splunk Search Head
* Saved Searches

# Setup

* Copy this application to a new folder in your `$SPLUNK_HOME$\etc\apps\` folder.
* Restart your splunk instance so the the app is loaded.

OR

* Download the splunk_rerun_app.tgz file
* Install from file through Splunk Web

# Parameters

The following is the list of parameters.

* regex - [required] Regex pattern to match against title of searches.
* trigger - [optional] Boolean value to trigger saved search actions or not.

# Usage:

```                  
| rerun regex="<Regex for Saved Search Titles>" trigger=<Boolean>
```

Rerun all searches that contain TEST-00 followed by any two digits somewhere in the title and trigger any alert actions

```
| rerun regex="TEST-00[0-9]{2}" trigger=t 
```

Rerun all saved searches to compare result count with what was actually received

```
| rerun regex=".*" 
```

# Issues

* Results are not returned until search is complete or script has exited.






