from apscheduler.schedulers.background import BackgroundScheduler

def start_scheduler():
    scheduler = BackgroundScheduler()
    # TODO: Add daily pipeline job at 4 PM
    scheduler.start()
    return scheduler
