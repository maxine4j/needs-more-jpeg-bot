#!/bin/bash
PIDFILE="/tmp/jpegbot.pid"

if [ -f "$PIDFILE" ];
then
	kill $(cat $PIDFILE)
	rm $PIDFILE
else
	echo "$PIDFILE does not exist"
	echo "not running"
fi
