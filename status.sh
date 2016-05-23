#!/bin/bash
PIDFILE="/tmp/jpegbot.pid"

if [ -f "$PIDFILE" ];
then
	echo "$PIDFILE exists"
	PID=$(cat $PIDFILE)
	echo "pid: $PID"
	ps up $PID  && echo "running" || echo "not running but lock file exists"
else
	echo "not running"
fi
