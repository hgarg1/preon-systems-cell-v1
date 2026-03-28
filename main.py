#import file libs

from random import random


reject_randomly = False

class Cell:
    def __init__(self, name, appetite, x, y):
        self.x = x
        self.y = y
        self.name = name
        self.appetite = appetite
        self.state = 1 #0 for dead, 1 for alive
    
    def eat(self, food, reject_randomly):
        if self.state == 0:
            return -1
        if food >= self.appetite:
            if reject_randomly and (random() < 0.1): #10% chance to reject food
                self.state = 0
                return -1
            else:
                self.state = 1
            food -= self.appetite
            return food
        else:
            self.state = 0
            return -1


def main(args):
    with open("universe.txt", "r") as f:
        data = f.read()    
    lines = data.splitlines()
    config = {}
    for line in lines:
        if "=" in line:
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()[:-1] #remove last character
            #remove quotes if exist
            if config[key.strip()][0] == '"' and config[key.strip()][-1] == '"':
                config[key.strip()] = config[key.strip()][1:-1]
    cell = Cell(config["cell_name"], int(config["cell_appetite"]), int(config["cell_x"]), int(config["cell_y"]))
    food = int(config["FOOD"])
    reject_randomly = config["REJECT_RANDOMLY"].lower() == "true"
    while cell.state == 1:
        food = cell.eat(food, reject_randomly)
        if food == -1:
            print(f"{cell.name} is dead.")
            break
        else:
            print(f"{cell.name} ate {cell.appetite} units of food. Remaining food: {food}")    
    return 0

if __name__ == "__main__":
    main(None)