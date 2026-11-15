#!/bin/bash
for i in 2 3 4 5; do ip netns pids sonar-ns$i 2>/dev/null | xargs -r kill 2>/dev/null; ip netns del sonar-ns$i 2>/dev/null; done
ip link del br-sonar 2>/dev/null
ip neigh flush 198.18.99.0/29 2>/dev/null
echo "netns down"
