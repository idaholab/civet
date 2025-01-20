#!/bin/bash
set -e
# Populate /var/civet and nginx
mkdir -p ${PREFIX}/var/civet/logs
mkdir -p ${PREFIX}/var/civet/civet
mkdir -p ${PREFIX}/etc/nginx/sites.d
mkdir -p ${PREFIX}/etc/nginx/ssl
touch ${PREFIX}/var/civet/logs/placeholder
touch ${PREFIX}/etc/nginx/sites.d/placeholder
touch ${PREFIX}/etc/nginx/ssl/placeholder

# Move Civet into place
mv civet/* ${PREFIX}/var/civet/civet
mv civet_recipes ${PREFIX}/var/civet/

# Conda Easy Settings.py overlay
cat <<EOF >> "${PREFIX}/var/civet/civet/civet/settings.py"
postgresql_database = {'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'civet',
        }
DATABASES = {'default': postgresql_database}
EOF

# Create Nginx site conf
cat <<EOF > "${PREFIX}/etc/nginx/sites.d/civet.conf"
server {
  listen 3456 ssl;
  server_name  localhost;
  ssl_certificate ${PREFIX}/etc/nginx/ssl/localhost.cert;
  ssl_certificate_key ${PREFIX}/etc/nginx/ssl/localhost.key;
  ssl_protocols       TLSv1 TLSv1.1 TLSv1.2;
  ssl_ciphers         HIGH:!aNULL:!MD5;
  access_log ${PREFIX}/var/civet/logs/nginx_access.log;
  error_log ${PREFIX}/var/civet/logs/nginx_error.log;
  location = /favicon.ico { access_log off; log_not_found off; }
  location /static {
    root ${PREFIX}/var/civet/civet;
  }
  location / {
    include uwsgi_params;
    uwsgi_pass unix:${PREFIX}/var/civet/logs/civet_uwsgi.sock;
  }
}
EOF

# Create uwsgi conf
cat <<EOF >"${PREFIX}/var/civet/uwsgi.ini"
[uwsgi]
chdir=${PREFIX}/var/civet/civet
module=civet.wsgi:application
home=${PREFIX}
master=True
vacuum=True
max-requests=200
buffer-size=30000
daemonize=${PREFIX}/var/civet/logs/civet_uwsgi.log
log-reopen=True
pidfile=${PREFIX}/var/civet/logs/civet_uwsgi.pid
socket=${PREFIX}/var/civet/logs/civet_uwsgi.sock
processes=4
disable-logging=True
lazy-apps=True
http-timeout=3000
harakiri=30
EOF

#### Create Activation/Deactivaion scripts
mkdir -p "${PREFIX}/etc/conda/activate.d" "${PREFIX}/etc/conda/deactivate.d"
cat <<EOF > "${PREFIX}/etc/conda/activate.d/activate_${PKG_NAME}.sh"
# Modify the default nginx.conf to not saturate the node with workers
if [ "\$(grep -c 'worker_processes 4' ${PREFIX}/etc/nginx/nginx.conf)" -le 0 ]; then
    if [ \`uname\` == "Dawrin" ]; then
        sed -i '' -e "s|worker_processes auto|worker_processes 4|g" ${PREFIX}/etc/nginx/nginx.conf
    else
        sed -i'' -e "s|worker_processes auto|worker_processes 4|g" ${PREFIX}/etc/nginx/nginx.conf
    fi
fi

# Generate SSL Self Signed Certificate
if [ ! -f ${PREFIX}/etc/nginx/ssl/localhost.key ] || [ ! -f ${PREFIX}/etc/nginx/ssl/localhost.cert ]; then
    rm -f ${PREFIX}/etc/nginx/ssl/localhost.key ${PREFIX}/etc/nginx/ssl/localhost.cert
    printf "Generating self-signed SSL Certificate/Key...\n\n"
    openssl req -new -newkey rsa:4096 -days 365 -nodes -x509 \
      -subj "/C=US/ST=Idaho/L=Idaho Falls/O=private_instance/CN=localhost" \
      -keyout ${PREFIX}/etc/nginx/ssl/localhost.key \
      -out ${PREFIX}/etc/nginx/ssl/localhost.cert &>/dev/null
fi

# Make sure civet_recipes is a repo (a civet requirement sadly)
if [ ! -d ${PREFIX}/var/civet/civet_recipes/.git ]; then
    OLDPWD=\`pwd\`
    cd ${PREFIX}/var/civet/civet_recipes
    git init . &> /dev/null
    git add * &> /dev/null
    # ignore potential ~/.gitconfig
    HOME= git -c user.name='no one' -c user.email='my@email.org' commit -m 'initial commit' &> /dev/null
    cd \$OLDPWD
fi
if [ ! -L ${PREFIX}/var/civet/civet/static ]; then
    OLDPWD=\`pwd\`
    cd ${PREFIX}/var/civet/civet
    ln -s ci/static .
    cd \$OLDPWD
fi
# Postgres init/start routines
if command -v pg_ctl &> /dev/null; then
    export PGDATA=${PREFIX}/var/postgres/pgdata
    export PGHOST=\${PGDATA}/sockets
    if [ ! -d \${PGDATA} ]; then
        OLDPWD=\`pwd\`
        # Create Postgres structure and start server
        mkdir -p \${PGDATA}
        pg_ctl init &> /dev/null
        mkdir -p \${PGHOST}
        echo "unix_socket_directories = 'sockets'" >> "\${PGDATA}/postgresql.conf"
        echo "listen_addresses = ''" >> "\${PGDATA}/postgresql.conf"
        pg_ctl start &> /dev/null
        export PGUSER=\`whoami\`
        export PGDATABASE=civet
        createdb civet &> /dev/null
        cd ${PREFIX}/var/civet/civet
        ./manage.py makemigrations &> /dev/null
        ./manage.py migrate &> /dev/null
        ./manage.py load_recipes &> /dev/null
        pg_ctl stop &> /dev/null
        cd \$OLDPWD
        printf "Postgres ready. Please reactivate your environment:\n\n\tconda deactivate; conda activate \${CONDA_DEFAULT_ENV}\n"
    else
        # Start the server
        if [ \$(${PREFIX}/bin/pg_ctl status | grep -c 'no server running') -ge 1 ]; then
            pg_ctl start &> /dev/null
            printf "Postgres started\n"
            uwsgi ${PREFIX}/var/civet/uwsgi.ini &> /dev/null
            nginx &> /dev/null &
            printf "\nCivet listing on:\n\thttps://localhost:3456\n\n"
            printf "Civet source can be modified in:\n\t\${CONDA_PREFIX}/var/civet/civet\n\n"
        fi
    fi
else
    printf "Please install the following:\n\n\tconda install postgresql\n\nand reactivate your environment.\n"
fi
EOF

cat <<EOF > "${PREFIX}/etc/conda/deactivate.d/deactivate_${PKG_NAME}.sh"
if [ \$(${PREFIX}/bin/pg_ctl status | grep -c 'is running') -ge 1 ]; then
    ${PREFIX}/bin/pg_ctl stop &> /dev/null
    ${PREFIX}/bin/nginx -s quit &> /dev/null
    ${PREFIX}/bin/uwsgi --stop ${PREFIX}/var/civet/logs/civet_uwsgi.pid &> /dev/null
    printf "Postgres stopped\n"
fi
unset PGDATA PGHOST
EOF
