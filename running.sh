#!/bin/bash
PIDFILE="/tmp/jpegbot.pid"

if [ -f "$PIDFILE" ];
then
	echo "$PIDFILE exists"
	PID=$(cat $PIDFILE)
	echo "pid: $PID"
	ps up $PID  && echo "true" || echo "false"
else
	echo "false"
fi
