import time
import sys
import signal
import os
from service import Service

EXIT_STATUS = False

def exit_gracefully(signum, frame):
    print('received signal %d' % signum)
    EXIT_STATUS = True
    #sys.exit(0)
    return

def my_task():
    #signal.signal(signal.SIGTERM, exit_gracefully)
    """
    这是你的任务
    """
    for i in range(10):
        print('ok, i=%d' % i)
        time.sleep(5)
        if EXIT_STATUS:
            break
    return



class TaskService(Service):
    def __init__(self, *args, **kwargs):
        super(TaskService, self).__init__(*args, **kwargs)

    def run(self):
        #signal.signal(signal.SIGINT, self.exit_gracefully)
        #signal.signal(signal.SIGINT, exit_gracefully)
        #signal.signal(signal.SIGTERM, exit_gracefully)
        #signal.signal(signal.SIGQUIT, exit_gracefully)
        #signal.signal(signal.SIGHUP, exit_gracefully)
        my_task()

if __name__ == '__main__':

    if len(sys.argv) != 2:
        sys.exit('Syntax: %s COMMAND' % sys.argv[0])

    cmd = sys.argv[1].lower()
    service = TaskService('my_service', pid_dir='/tmp')

    if cmd == 'start':
        service.start()
    elif cmd == 'stop':
        try :
            service.stop()
        except Exception as e:
            print('stop error:{}'.format(e))
    elif cmd == 'kill':
        service.kill()
    elif cmd == 'pid':
        print(service.get_pid())
    elif cmd == 'status':
        if service.is_running():
            print("Service is running.")
        else:
            print("Service is not running.")
    else:
        sys.exit('Unknown command "%s".' % cmd)