#!/bin/bash
# Private test network on the box: bridge br-sonar 198.18.99.1/29 (RFC 2544
# benchmark range, not routed anywhere) + 4 namespaces with fixed MACs.
set -e
D=$(dirname "$(realpath "$0")")
ip link add br-sonar type bridge 2>/dev/null || true
ip addr replace 198.18.99.1/29 dev br-sonar
ip link set br-sonar up
declare -A MAC=([2]=00:50:56:1a:2b:02 [3]=b8:27:eb:3c:4d:03 [4]=00:1a:11:5e:6f:04 [5]=52:54:00:7a:8b:05)
for i in 2 3 4 5; do
  ns=sonar-ns$i
  ip netns add $ns 2>/dev/null || true
  ip link add v$i-h type veth peer name v$i-n 2>/dev/null || true
  ip link set v$i-n netns $ns 2>/dev/null || true
  ip link set v$i-h master br-sonar up
  ip netns exec $ns ip link set lo up
  ip netns exec $ns ip link set v$i-n address ${MAC[$i]}
  ip netns exec $ns ip addr replace 198.18.99.$i/29 dev v$i-n
  ip netns exec $ns ip link set v$i-n up
done
# services
ip netns exec sonar-ns2 python3 -m http.server 80 --bind 198.18.99.2 >/dev/null 2>&1 &
ip netns exec sonar-ns2 python3 $D/nbns_responder.py 198.18.99.2 FILESRV01 LAB >/dev/null 2>&1 &
ip netns exec sonar-ns3 python3 $D/listen.py 198.18.99.3 22 >/dev/null 2>&1 &
ip netns exec sonar-ns4 python3 $D/listen.py 198.18.99.4 443 >/dev/null 2>&1 &
sleep 1
echo "netns up: 198.18.99.2-5 (ns2: http 80 + NetBIOS FILESRV01/LAB, ns3: 22, ns4: 443, ns5: nothing)"
