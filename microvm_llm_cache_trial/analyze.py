#!/usr/bin/env python3
"""Exploratory two-class held-out classification (12 train / 8 test).

Run on host after copying observer.csv out of a powered-off VM2.
Warning: this is not a vulnerability proof. Requires no-victim & private-backing controls.
"""
import csv
import math
import sys
import statistics
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("Usage: python3 analyze.py observer.csv trial_labels.txt")
obs, label_file = map(Path, sys.argv[1:])
labels = [line.strip() for line in label_file.read_text().splitlines() if line.strip()]
by_slot = {}
with obs.open(newline='') as f:
    for r in csv.DictReader(f):
        s = int(r['slot'])
        by_slot.setdefault(s, []).append((int(r['red_ns']), int(r['blue_ns'])))

def p10(v):
    return sorted(v)[int((len(v)-1)*.1)]

points = []
for i, label in enumerate(labels):
    records = by_slot.get(i, [])
    if not records:
        raise SystemExit(f"Missing measurements for slot {i}")
    red = p10([v[0] for v in records])
    blue = p10([v[1] for v in records])
    score = blue - red    # larger = red relatively faster
    points.append((label, score, len(records), red, blue))

ntrain = (len(points)*3)//5
train, test = points[:ntrain], points[ntrain:]
red_train = [p[1] for p in train if p[0] == 'red']
blue_train = [p[1] for p in train if p[0] == 'blue']
if not red_train or not blue_train or not test:
    raise SystemExit('Need both labels in training and nonempty test')
red_mean = statistics.mean(red_train)
blue_mean = statistics.mean(blue_train)
threshold = (red_mean + blue_mean)/2
red_higher = red_mean > blue_mean

def predict(score):
    return 'red' if ((score >= threshold) == red_higher) else 'blue'

correct = 0
print('slot  truth   score(blue_p10-red_p10)  predicted  n  red_p10  blue_p10')
for i, (label, score, n, rp, bp) in enumerate(points):
    if i >= ntrain:
        pred = predict(score)
        correct += int(pred == label)
    else:
        pred = '(train)'
    print(f'{i:>3}  {label:<5} {score:>9} ns              {pred:<8} {n:>3} {rp:>6} {bp:>6}')
n = len(test)
p = sum(math.comb(n, k) for k in range(correct, n+1)) / (2**n)
print(f'\nTraining slots: {ntrain}, test slots: {n}')
print(f'Training red mean score={red_mean:.1f}, blue mean score={blue_mean:.1f}, cutoff={threshold:.1f}')
print(f'HELD-OUT ACCURACY: {correct}/{n} = {correct/n:.1%}')
print(f'Naive one-sided Binomial(0.5) tail p={p:.5f}')
print('CAUTION: exploratory proxy test, not established cross-VM leakage.')
print('Repeat with no-victim, different backing files, and multiple randomized sessions.')
