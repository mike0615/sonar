# Sonar Help

_This file mirrors Help > Sonar Help (F1) in the app._

Sonar finds the devices on a network. Enter an address range, press Start, and Sonar pings every address in parallel. For each host that answers it shows the response time, host name (reverse DNS), MAC address and vendor, NetBIOS name and workgroup, and which of your chosen TCP ports are open. It never needs root.

Quick start

1. Type a range in the Range box: 10.0.0.1-254, 10.0.0.0/24, 10.0.0.*, or several separated by commas. Ctrl+L fills in this computer's own subnet.
2. Press Start (F5). Hosts appear as they answer; the progress bar shows how many addresses are done. Press Stop (Esc) at any time.
3. Right-click a host to copy its address, ping it, open it in a web browser, or open it in Skiff or MultiSSH Manager.
4. File > Export saves the table as CSV, text, HTML or XML.

Only scan networks you own or are allowed to scan.

## Keyboard shortcuts

| Keys | Action |
|---|---|
| `F1` | This help |
| `F5 / Ctrl+Enter` | Start the scan |
| `Esc` | Stop the scan |
| `Ctrl+L` | Fill in this computer's own subnet |
| `Ctrl+F` | Filter the results |
| `Ctrl+E` | Export results |
| `Ctrl+D` | Add the selected host to Favourites |
| `Ctrl+B` | Save the current range |
| `Ctrl+C` | Copy the selected IP addresses |
| `Ctrl+,` | Preferences |
| `Ctrl+Q` | Quit |

## Address ranges

The Range box accepts any mix of these, separated by commas, semicolons or spaces:

```
192.0.2.10            one address
192.0.2.1-192.0.2.40  a start and end address
192.0.2.1-254         a start address and the last octet of the end
192.0.2.0/24          a CIDR block (network and broadcast are skipped)
192.0.2.*             the same as 192.0.2.1-254
```

One scan can cover up to 65,536 addresses. Duplicates are scanned once.

## How hosts are found

Sonar pings each address. It picks the first ping method that works for your account, so it never needs root:

```
icmp  an unprivileged ICMP echo socket (Rocky allows this for all users by default through net.ipv4.ping_group_range)
ping  the system /usr/bin/ping
tcp   a TCP connect to a few common ports; a host that accepts or refuses the connection is up
```

The status bar shows the method in use. Force one in Preferences or with ping_method in sonar.conf. Hosts that block ICMP and every probe port show as down; turn on "Show dead hosts" to list every address.

## Columns

IP Address - the host's IPv4 address. Response - round-trip time of the ping (or of the first TCP answer). Host Name - reverse DNS (PTR) name, if your DNS server has one. MAC Address - from this computer's ARP table, so it is only known for hosts on the same subnet (routers hide the MAC of hosts further away). If ARP has nothing, the MAC from a NetBIOS reply is used. Vendor - manufacturer from the IEEE OUI list in /usr/share/hwdata/oui.txt (hwdata package). "(locally administered)" means a random or virtual MAC. NetBIOS Name / Workgroup - from a NetBIOS node status query (UDP 137). Windows PCs, Samba servers and many NAS boxes answer. Open Ports - TCP ports from your port list that accepted a connection.

## Results table

Click a column header to sort; IP addresses sort numerically. Type in the Filter box (Ctrl+F) to show only rows containing that text in any column. "Alive only" hides hosts that did not answer (only relevant when Show dead hosts is on). Select several rows with Shift or Ctrl.

## Right-click actions

Copy IP address - copies the selected addresses, one per line. Copy row - copies the selected rows as tab-separated text. Ping - runs ping -c 4 and shows the output in a window. Open in browser (http / https) - opens http://IP or https://IP. Open in Skiff - opens the host in the Skiff SFTP client. Open in MultiSSH Manager - opens the host in MultiSSH Manager. Add to Favourites - keeps the host in the Favourites list.

The Skiff and MultiSSH Manager entries are greyed out when that program cannot be found. See "Skiff and MultiSSH Manager" for exactly what each one does.

## Skiff and MultiSSH Manager

Sonar finds both programs through the master configuration file (skiff_path and multissh_path). If a path is wrong, Sonar falls back to the program name on PATH.

Open in Skiff: Skiff has no host option on its command line yet, so Sonar adds a site called "Sonar: <ip>" to Skiff's Site Manager (~/.config/skiff/sites.json; the host, SSH port and user name come from Preferences) unless a site for that host already exists, then starts Skiff. Press Ctrl+S in Skiff and double-click the site. Set skiff_add_site = no to only start Skiff.

Open in MultiSSH Manager: MultiSSH Manager opens a session file given on its command line, so Sonar writes a one-host session file to ~/.cache/sonar/multissh/sonar-<ip>.json and starts multissh-manager <that file>. Double-click the host in the Sonar folder to connect. Your own sessions file is not touched; use File > Save As in MultiSSH Manager to keep the entry, or import it later.

## Saved ranges and favourites

Ranges > Save current range (Ctrl+B) names the text in the Range box and lists it under Ranges; pick it to load it again. Ranges > Manage renames or deletes them.

Favourites keeps hosts you look up often. Add one from the right-click menu (Ctrl+D). Favourites > Scan favourites rescans only those hosts.

Both lists are JSON files in ~/.config/sonar/.

## Export

File > Export (Ctrl+E) writes the rows currently shown (after the filter and Alive only) to:

```
CSV  - for spreadsheets
TXT  - aligned columns for reading or email
HTML - a styled table for a browser
XML  - one <host> element per address with <ports> children
```

## Master configuration file

System defaults live in /etc/sonar/sonar.conf (INI format, installed by the RPM; root edits it). Each user can override any key in ~/.config/sonar/sonar.conf. Edit > Preferences writes only the keys you change into the user file.

[scan]

```
threads = 64             hosts probed at the same time (1-512)
timeout_ms = 1000        ping and connect timeout
ping_method = auto       auto, icmp, ping or tcp
probe_ports = 80,443,... ports used by the TCP ping
ports = 21,22,...        ports checked on live hosts; ranges allowed
scan_ports / resolve_hostnames / netbios / show_dead = yes|no
```

[launchers]

```
skiff_path = /usr/bin/skiff
multissh_path = /usr/bin/multissh-manager
default_user =           blank = your login name
ssh_port = 22
skiff_add_site = yes
skiff_args =             extra arguments; {host} {user} {port}
multissh_args = {session_file}
browser_command =        blank = desktop default; {url}
```

## Speed and timeouts

A /24 with the defaults takes a few seconds. Raise threads for big ranges; lower timeout_ms on a fast LAN (200-300 ms is plenty) or raise it over a VPN. Port scans run on live hosts only, 32 ports at a time per host, so a long port list costs roughly (ports / 32) x timeout per host.

## Not included

SNMP queries and listing shared folders (SMB shares) are not included: both need extra libraries that are not in the stock Rocky repositories. Wake-on-LAN, remote shutdown and IPv6 scanning are not included either.

## Troubleshooting

Every host shows as up with no open ports: some networks answer TCP probes for every address (a firewall sending resets). Switch ping_method to icmp or ping.

Nothing answers: check that the range is on a network you can reach, and raise timeout_ms.

No MAC addresses: MACs are only visible for hosts on your own subnet.

Vendor is blank: install hwdata (dnf install hwdata).

"Open in Skiff" is greyed out: install Skiff, or set skiff_path in Preferences.
