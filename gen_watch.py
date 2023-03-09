from confgen.watcher import Watcher

watcher = Watcher()

# generate initial config on startup
watcher.generate_config()

# watch for future changes
watcher.begin_watch()
