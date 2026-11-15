#!/usr/bin/env bash
# Build the Sonar SRPM + noarch RPM inside a Rocky Linux 9 or 10 container or
# chroot with the source tree at $WORK (default /work). Output: $WORK/out/.
set -euo pipefail
WORK="${WORK:-/work}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "${WORK}/sonar/__init__.py")"
dnf -y -q install rpm-build python3 tar gzip desktop-file-utils
TOP=/root/rpmbuild
rm -rf ${TOP}; mkdir -p ${TOP}/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
cd "${WORK}"
tar --exclude=.git --exclude=out --exclude='__pycache__' --exclude='*.pyc' \
    --transform "s,^,sonar-${VERSION}/," \
    -czf ${TOP}/SOURCES/sonar-${VERSION}.tar.gz \
    sonar bin packaging tests docs README.md HELP.md LICENSE .gitignore build.sh
sed "s/\r$//" packaging/sonar.spec > ${TOP}/SPECS/sonar.spec
rpmbuild -ba --define "_topdir ${TOP}" ${TOP}/SPECS/sonar.spec
mkdir -p "${WORK}/out"
cp -v ${TOP}/RPMS/noarch/sonar-*.rpm ${TOP}/SRPMS/sonar-*.src.rpm ${TOP}/SOURCES/sonar-${VERSION}.tar.gz "${WORK}/out/"
