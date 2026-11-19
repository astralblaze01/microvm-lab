#!/usr/bin/env bash
set -euo pipefail

ARCH="$(uname -m)"
S3="https://s3.amazonaws.com/spec.ccfc.min"

if [ "$ARCH" != "aarch64" ]; then
    echo "ARM64 환경이 아닙니다."
    exit 1
fi

PREFIX=$(curl -fsSL \
  "$S3?list-type=2&prefix=firecracker-ci/&delimiter=/" \
  | grep -oP '(?<=<Prefix>)firecracker-ci/[0-9]{8}-[^/]+/(?=</Prefix>)' \
  | sort | tail -1)

[ -n "$PREFIX" ] || {
    echo "CI 아티팩트 목록을 찾지 못했습니다."
    exit 1
}

KERNEL=$(curl -fsSL \
  "$S3?list-type=2&prefix=${PREFIX}${ARCH}/vmlinux-" \
  | grep -oP "(?<=<Key>)(${PREFIX}${ARCH}/vmlinux-[0-9]+\.[0-9]+\.[0-9]{1,3})(?=</Key>)" \
  | sort -V | tail -1)

ROOTFS=$(curl -fsSL \
  "$S3?list-type=2&prefix=${PREFIX}${ARCH}/ubuntu-" \
  | grep -oP "(?<=<Key>)(${PREFIX}${ARCH}/ubuntu-[0-9]+\.[0-9]+\.squashfs)(?=</Key>)" \
  | sort -V | tail -1)

[ -n "$KERNEL" ] && [ -n "$ROOTFS" ] || {
    echo "ARM64 커널 또는 rootfs를 찾지 못했습니다."
    exit 1
}

echo "Kernel: $KERNEL"
echo "Rootfs: $ROOTFS"

curl -fL "$S3/$KERNEL" -o guest-kernel
curl -fL "$S3/$ROOTFS" -o guest.squashfs

sudo unsquashfs -d guest-root guest.squashfs

truncate -s 2G guest.ext4
sudo mkfs.ext4 -F -d guest-root guest.ext4

echo "VM 이미지 준비 완료"
ls -lh guest-kernel guest.squashfs guest.ext4
