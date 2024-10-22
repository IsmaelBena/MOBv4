import itertools
from random import SystemRandom as sr

class TeamsManager():
    def __init__(self):
        self.session = None
        self.all_players = []
        self.team_sizes = []
        self.team_names = []
        
        
    def add_players(self, players):
        if len(self.team_sizes) < 2:
            self.all_players.append(players)
        else:
            if len(self.all_players)
        
        print(f"current players: {self.all_players}")
    
    def generate_permutations(self):
        self.all_permutations = list(itertools.permutations(self.all_players))
        
    