__author__ = 'amazadonde'


class Agent:
    def __init__(self, name, uri, address, stop):
        self.name = name
        self.uri = uri
        self.address = address
        self.stop = stop

class Agent2:
    def __init__(self, name, uri, address, diference, stop):
        self.name = name
        self.uri = uri
        self.address = address
        self.diference = diference
        self.stop = stop





class City(object):
    def __init__(self, name, lat, long):
        self.name = name
        self.lat = lat
        self.long = long
