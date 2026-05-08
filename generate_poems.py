#!/usr/bin/env python3

# Generate poem 7 - Epic Journey
lines = []
for i in range(1, 2001):
    stanzas = [
        f'Through distant lands the traveler goes, verse {i}',
        f'Where ancient winds and wisdom blows, verse {i}',
        f'Across the plains and over seas, verse {i}',
        f'Through valleys deep and mountain trees, verse {i}',
    ]
    lines.append(stanzas[(i-1) % 4])

with open('poems/poem7.txt', 'w') as f:
    f.write('\n'.join(lines))
print('Created poem7.txt with 2000 lines')

# Generate poem 8 - The Cosmos
lines = []
for i in range(1, 2001):
    stanzas = [
        f'Among the stars that shine so bright, line {i}',
        f'Through galaxies of endless light, line {i}',
        f'The cosmos speaks in silent song, line {i}',
        f'Where mysteries and wonders throng, line {i}',
    ]
    lines.append(stanzas[(i-1) % 4])

with open('poems/poem8.txt', 'w') as f:
    f.write('\n'.join(lines))
print('Created poem8.txt with 2000 lines')

# Generate poem 9 - The Ocean's Tale
lines = []
for i in range(1, 2001):
    stanzas = [
        f'Beneath the waves where currents flow, part {i}',
        f'The ocean depths hold secrets below, part {i}',
        f'Where creatures strange and beautiful dwell, part {i}',
        f'With stories that the waters tell, part {i}',
    ]
    lines.append(stanzas[(i-1) % 4])

with open('poems/poem9.txt', 'w') as f:
    f.write('\n'.join(lines))
print('Created poem9.txt with 2000 lines')

# Generate poem 10 - Dreams and Memory
lines = []
for i in range(1, 2001):
    stanzas = [
        f'In dreams we find what memory keeps, section {i}',
        f'Through waking thoughts and when we sleep, section {i}',
        f'The echoes of the days gone by, section {i}',
        f'Like whispers soft, like lullaby, section {i}',
    ]
    lines.append(stanzas[(i-1) % 4])

with open('poems/poem10.txt', 'w') as f:
    f.write('\n'.join(lines))
print('Created poem10.txt with 2000 lines')

print('All poems created successfully!')
