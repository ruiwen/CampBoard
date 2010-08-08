PROJDIR=/home/ruiwen/Projects/CampBoard/
PIDDIR=${PROJDIR}bin/

if [ ! -f ${PIDDIR}tornado.pid ]; then
	python ${PROJDIR}campboard.py &
	echo $! > ${PIDDIR}tornado.pid
fi

if [ ! -f ${PIDDIR}nginx.conf ]; then
	nginx -c ${PROJDIR}nginx.conf &
	#echo $! > nginx.pid
fi
