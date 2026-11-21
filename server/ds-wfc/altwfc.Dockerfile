FROM python:2.7.18-slim-buster

WORKDIR /app

# AltWFC uses Python 2 and older Twisted. Keep it on a private network.
RUN pip install --no-cache-dir --only-binary=:all: 'Twisted==20.3.0' 'zope.interface==5.4.0'
ADD https://codeload.github.com/ubergeek77/dwc_network_server_emulator/tar.gz/68fcdb2989e57a10ec8cf8398ff7506c4c73d390 /tmp/altwfc.tar.gz
RUN tar -xzf /tmp/altwfc.tar.gz --strip-components=1 -C /app \
    && rm /tmp/altwfc.tar.gz \
    && sed -i -e "s/filename='gpcm.db'/filename='state\/gpcm.db'/" -e 's/logger_output_to_file = True/logger_output_to_file = False/' -e 's/logger_filename, -1,/logger_filename, logging.WARNING,/' gamespy/gs_database.py \
    && sed -i '/^        \(AdminPageServer\|RegPageServer\|InternalStatsServer\|StorageServer\|GameStatsServer\),$/d' master_server.py \
    && python -c "import ConfigParser; p='altwfc.cfg'; c=ConfigParser.RawConfigParser(); c.read(p); [c.set(s,'IP','0.0.0.0') for s in ('NasServer','GameSpyQRServer','GameSpyNatNegServer','GameSpyServerBrowserServer','GameSpyProfileServer','GameSpyPlayerSearchServer')]; [c.set(s,'LoggerOutputFile','OFF') for s in c.sections() if c.has_option(s,'LoggerOutputFile')]; [c.set(s,'LoggerLevel','20') for s in c.sections() if c.has_option(s,'LoggerLevel')]; f=open(p,'w'); c.write(f); f.close()" \
    && mkdir -p /app/state /app/logs \
    && chown 10001:10001 /app/state /app/logs

USER 10001:10001
CMD ["python", "master_server.py"]
