#!/bin/bash

PROJDIR=/home/ruiwen/Projects/CampBoard/
PIDDIR=${PROJDIR}bin/

kill `cat ${PIDDIR}tornado.pid`
kill `cat ${PIDDIR}nginx.pid`

rm ${PIDDIR}tornado.pid
