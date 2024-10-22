from random import SystemRandom as sr

z = False
f = False
while not (z and f):
    num = sr().randint(0, 5)
    if num == 0:
        z = True
        print(num)
    elif num == 5:
        f = True
        print(num)
        
        
def roll_dice(start=1, end=6):
    return sr().randint(start, end)