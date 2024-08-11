use clap::{arg, command};
use colored::Colorize;
use futures::future::join_all;
use rdp::core::client::Connector;
use std::{
    net::{SocketAddr, TcpStream},
    sync::Arc,
    time::Duration,
};
use tokio::{
    fs::{File, OpenOptions},
    io::{self, AsyncBufReadExt, AsyncWriteExt, BufReader},
    runtime::Builder,
    sync::Mutex,
    time::{timeout, Instant},
};

#[derive(Default)]
struct GlobalCounter {
    pub goods: usize,
    pub err: usize,
    pub timed_out: usize,
}

#[tokio::main]
async fn main() -> io::Result<()> {
    let matches = command!()
        .arg(arg!(-u --user <USERNAME> "Sets username").required(true))
        .arg(arg!(-p --password <PASSWORD> "Sets password").required(true))
        .arg(arg!(-p --proxy_pool <PROXY_POOL> "Sets proxy pool url"))
        .arg(
            arg!(-i --target_ips_file_name <TARGET_IPS_FILE_NAME> "Sets the target ips file name")
                .required(true),
        )
        .arg(
            arg!(-t --timeout <TIMEOUT> "Sets the connection timeout in millis")
                .required(true)
                .value_parser(clap::value_parser!(u64)),
        )
        .arg(
            arg!(--worker_threads <WORDER_THREADS> "Sets the worker threads count")
                .required(true)
                .value_parser(clap::value_parser!(usize)),
        )
        .get_matches();

    let mut opts = OpenOptions::new();
    let user = matches.get_one::<String>("user").unwrap().clone();
    let password = matches.get_one::<String>("password").unwrap().clone();
    let proxy_pool = matches.get_one::<String>("proxy_pool").cloned();
    let ips_file_name = matches.get_one::<String>("target_ips_file_name").unwrap();
    let timeout = *matches.get_one::<u64>("timeout").unwrap();
    let worker_threads = *matches.get_one::<usize>("worker_threads").unwrap();

    let ips = read_file_to_vec(ips_file_name).await?;

    let log_file = opts
        .write(true)
        .create(true)
        .truncate(true)
        .open("log.log")
        .await
        .unwrap();
    let log_file = Arc::new(Mutex::new(log_file));
    let glob_counter = Arc::new(Mutex::new(GlobalCounter::default()));

    let mut tasks = vec![];
    let now = Instant::now();
    let rt = Builder::new_multi_thread()
        .worker_threads(worker_threads)
        .enable_all()
        .build()
        .unwrap();
    let timeout = Duration::from_secs(timeout);

    for ip in ips {
        let user = user.clone();
        let password = password.clone();
        let proxy_pool = proxy_pool.clone();
        let log_file = log_file.clone();
        let glob_counter = glob_counter.clone();

        let task = rt.spawn(async move {
            process_ip(
                &ip,
                &user,
                &password,
                &proxy_pool,
                timeout,
                log_file,
                glob_counter,
            )
            .await;
        });

        tasks.push(task);
    }

    join_all(tasks).await;

    let glob_counter_guard = glob_counter.lock().await;
    let results = format!(
        "goods: {}, err: {}, timed out: {}, all: {}",
        glob_counter_guard.goods,
        glob_counter_guard.err,
        glob_counter_guard.timed_out,
        glob_counter_guard.goods + glob_counter_guard.err + glob_counter_guard.timed_out
    );

    let elapsed = now.elapsed();
    let elapsed_data = format!("время выполнения: {elapsed:.2?}");

    write_log(&log_file, &results).await;
    write_log(&log_file, &elapsed_data).await;

    rt.shutdown_background();

    Ok(())
}

#[allow(clippy::too_many_arguments)]
async fn process_ip(
    ip: &str,
    user: &str,
    pass: &str,
    proxy_pool: &Option<String>,
    timeout_duration: Duration,
    log_file: Arc<Mutex<File>>,
    glob_counter: Arc<Mutex<GlobalCounter>>,
) {
    let address = format!("{ip}:3389")
        .parse::<SocketAddr>()
        .map_err(|e| e.to_string())
        .unwrap();
    let stream =
        match TcpStream::connect_timeout(&address, timeout_duration).map_err(|e| e.to_string()) {
            Ok(s) => s,
            Err(e) => {
                let res_data = format!("connect err: {e}: {ip} {user} {pass}").red();

                write_log(&log_file, &res_data).await;
                glob_counter.lock().await.err += 1;

                return;
            }
        };

    let mut rdp_connector = Connector::new()
        .screen(800, 600)
        .credentials(String::new(), user.to_string(), pass.to_string())
        .set_restricted_admin_mode(false)
        .auto_logon(false)
        .check_certificate(false);

    let connection_future = tokio::task::spawn_blocking(move || {
        rdp_connector.connect(stream).map_err(|e| format!("{e:?}"))
    });

    let result = timeout(timeout_duration, async {
        let res = connection_future
            .await
            .unwrap_or_else(|e| Err(e.to_string()));
        res
    })
    .await;

    match result {
        Ok(Ok(_)) => {
            let res_data = format!("ok: {ip} {user} {pass}").green();
            println!("{res_data}");

            write_log(&log_file, &res_data).await;
            glob_counter.lock().await.goods += 1;
        }
        Ok(Err(_)) => {
            let res_data = format!("err: {ip} {user} {pass}").red();

            write_log(&log_file, &res_data).await;
            glob_counter.lock().await.err += 1;
        }
        Err(_) => {
            let res_data = format!("timed out: {ip} {user} {pass}");
            write_log(&log_file, &res_data).await;
            glob_counter.lock().await.timed_out += 1;
        }
    }
}

async fn read_file_to_vec(path: &str) -> io::Result<Vec<String>> {
    let file = File::open(path).await?;
    let reader = BufReader::new(file);

    let mut lines_stream = reader.lines();
    let mut lines: Vec<String> = Vec::new();

    while let Some(line) = lines_stream.next_line().await? {
        lines.push(line);
    }

    Ok(lines)
}

async fn write_log(log_file: &Arc<Mutex<File>>, data: &str) {
    log_file
        .lock()
        .await
        .write_all(format!("{data}\n").as_bytes())
        .await
        .unwrap();
}
