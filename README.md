# Strava API Thing


This is a notebook to explore the Strava API, as well as performing various 
functions against data.


## TODO

Explore various .fit file decoders:

* https://pypi.org/project/fitdecode/
* https://developer.garmin.com/fit/example-projects/python/
* https://github.com/dtcooper/python-fitparse

Explore whether or not I can "match" a workout file to an actual effort (Dynamic Time Warping)

* https://makeabilitylab.github.io/physcomp/signals/ComparingSignals/index.html
* https://www.theaidream.com/post/dynamic-time-warping-dtw-algorithm-in-time-series
* https://dsp.stackexchange.com/questions/76673/what-algorithm-can-i-use-to-compare-two-signals-similarity
* https://stackoverflow.com/questions/54278721/comparing-multiple-signals-for-similarity

ML Stuff?

* Use something like [Pycaret](https://pycaret.org/) to build some sort of model (time, heartrate, cadence, power) as inputs.



## Resources

* Strava Developer Docs: https://developers.strava.com/docs/getting-started/
    * Application Settings: https://www.strava.com/settings/api
    * Activity Streams: https://developers.strava.com/docs/reference/#api-Streams-getActivityStreams
    * Stream Sets: https://developers.strava.com/docs/reference/#api-models-StreamSet
* Jupyter: https://jupyter.org/install
