# -*- coding: utf-8 -*-

"""
Agente usando los servicios web de Flask
/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente
Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente
Asume que el agente de registro esta en el puerto 9000
"""
import argparse
import socket
import sys
import threading
from multiprocessing import Queue, Process
from time import sleep

from flask import Flask, request
from rdflib import URIRef, XSD

from utils.ACLMessages import *
from utils.Agent import Agent
from utils.FlaskServer import shutdown_server
from utils.Logging import config_logger
from utils.OntologyNamespaces import ECSDI
__author__ = 'ECSDIstore'

# Definimos los parametros de la linea de comandos
parser = argparse.ArgumentParser()
parser.add_argument('--open', help="Define si el servidor est abierto al exterior o no", action='store_true',
                    default=False)
parser.add_argument('--port', type=int, help="Puerto de comunicacion del agente")
parser.add_argument('--dhost', default=socket.gethostname(), help="Host del agente de directorio")
parser.add_argument('--dport', type=int, help="Puerto de comunicacion del agente de directorio")

# Logging
logger = config_logger(level=1)

# parsing de los parametros de la linea de comandos
args = parser.parse_args()

# Configuration stuff
if args.port is None:
    port = 9011
else:
    port = args.port

if args.open is None:
    hostname = '0.0.0.0'
else:
    hostname = socket.gethostname()

if args.dport is None:
    dport = 9000
else:
    dport = args.dport

if args.dhost is None:
    dhostname = socket.gethostname()
else:
    dhostname = args.dhost

# AGENT ATTRIBUTES ----------------------------------------------------------------------------------------

# Agent Namespace
agn = Namespace("http://www.agentes.org#")

# Message Count
mss_cnt = 0

# Data Agent
# Datos del Agente
CentroLogisticoAgent = Agent('CentroLogisticoAgent',
                    agn.CentroLogisticoAgent,
                    'http://%s:%d/comm' % (hostname, port),
                    'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))

CentroLogisticoDirectoryAgent = Agent('CentroLogisticoDirectoryAgent',
                       agn.CentroLogisticoDirectory,
                       'http://%s:9010/Register' % (hostname),
                       'http://%s:9010/Stop' % (hostname))

# Global triplestore graph
dsGraph = Graph()

# Queue
queue = Queue()

# Flask app
app = Flask(__name__)

#función inclremental de numero de mensajes
def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio
    :param gmess:
    :return:
    """

    logger.info('Nos registramos')
    gr = registerAgent(CentroLogisticoAgent, CentroLogisticoDirectoryAgent, CentroLogisticoAgent.uri, getMessageCount())
    gr = registerAgent(CentroLogisticoAgent, DirectoryAgent, CentroLogisticoAgent.uri, getMessageCount())
    return gr

@app.route("/comm")
def communication():
    """
    Communication Entrypoint
    """

    logger.info('Peticion de envio recibida')
    global dsGraph

    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)

    messageProp = get_message_properties(grafoEntrada)

    if messageProp is None:
        # Si no es, respondemos que no hemos entendido el mensaje
        res = build_message(Graph(), ACL['not-understood'], sender=CentroLogisticoAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProp['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            res = build_message(Graph(),
                               ACL['not-understood'],
                               sender=CentroLogisticoDirectoryAgent.uri,
                               msgcnt=getMessageCount())
        else:
            content = messageProp['content']
            # Averiguamos el tipo de la accion
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)

            print(accion)

            if accion == ECSDI.PeticionEnvioACentroLogistico:

                logger.info('Peticion Envio A Centro Logistico')

                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))

                faltan = responderPeticionEnvio(grafoEntrada, content)
                res = faltan

    logger.info('Respondemos a la petición de envio')
    serialize = res.serialize(format='xml')
    return serialize, 200



def responderPeticionEnvio(grafoEntrada, content):

    prioritat = grafoEntrada.value(subject=content, predicate=ECSDI.Prioridad)

    relacion = grafoEntrada.value(subject=content, predicate=ECSDI.EnvioDe)
    direccion = grafoEntrada.value(subject=relacion, predicate=ECSDI.Destino)
    direccion2 = grafoEntrada.value(subject=direccion, predicate=ECSDI.Direccion)
    codigopostal = grafoEntrada.value(subject=direccion, predicate=ECSDI.CodigoPostal)

    print("Prioritat, relacio i direccio")
    print(prioritat)
    print(relacion)
    print(direccion)

    grafoFaltan = Graph()
    grafoFaltan.bind('ECSDI', ECSDI)
    contentR = ECSDI['RespuestaEnvioDesdeCentroLogistico' + str(getMessageCount())]
    grafoFaltan.add((contentR, RDF.type, ECSDI.RespuestaEnvioDesdeCentroLogistico))
    grafoFaltan.add((contentR, ECSDI.Prioridad, Literal(prioritat, datatype=XSD.int)))

    for producto in grafoEntrada.objects(subject=relacion, predicate=ECSDI.Contiene):
        nombreP = grafoEntrada.value(subject=producto, predicate=ECSDI.Nombre)

        # QUERY
        # Mirar que el que retorna la query sigui un stock amb num de tal >= 1

        graph = Graph()
        ontologyFile = open('../data/StockDB')
        graph.parse(ontologyFile, format='turtle')

        addAnd = False;

        query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                            PREFIX owl: <http://www.w3.org/2002/07/owl#>
                            PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
                            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                            SELECT ?Stock ?Producto ?Nombre ?Descripcion ?Precio ?Peso ?UnidadesEnStok
                            where {
                                ?Stock rdf:type default:Stock .
                                ?Stock default:UnidadesEnStok ?UnidadesEnStok .
                                ?Stock default:Tiene ?Producto .
                                ?Producto default:Nombre ?Nombre .
                                ?Producto default:Descripcion ?Descripcion .
                                ?Producto default:Precio ?Precio .
                                ?Producto default:Peso ?Peso .
                                FILTER("""

        if nombreP is not None:
            query += """?Nombre = '""" + nombreP + """'"""
            addAnd = True

        query += """)}"""

        graph_query = graph.query(query)

        for a in graph_query:
            print(a)

        for stock in graph_query:
            unitats = stock.UnidadesEnStok
            producto = stock.Producto
            descripcion = stock.Descripcion
            nombre = stock.Nombre
            precio = stock.Precio
            peso = stock.Peso

            print(unitats)
            print(producto)
            print(descripcion)
            print(nombre)
            print(precio)
            print(peso)


            if unitats == 0:
                grafoFaltan.add((producto, RDF.type, ECSDI.Producto))
                grafoFaltan.add((producto, ECSDI.Descripcion, Literal(descripcion, datatype=XSD.string)))
                grafoFaltan.add((producto, ECSDI.Nombre, Literal(nombre, datatype=XSD.string)))
                grafoFaltan.add((producto, ECSDI.Precio, Literal(precio, datatype=XSD.string)))
                grafoFaltan.add((producto, ECSDI.Peso, Literal(peso, datatype=XSD.string)))
                grafoFaltan.add((contentR, ECSDI.Faltan, URIRef(producto)))

            else:
                ontologyFile = open("../data/ProductosPendientesDB")
                grafoPendientes = Graph()
                grafoPendientes.parse(ontologyFile, format='turtle')

                grafoEnviar = Graph()
                grafoEnviar.bind('ECSDI', ECSDI)

                contentEnviar = ECSDI['ProductoPendiente' + str(getMessageCount())]
                grafoEnviar.add((contentEnviar, RDF.type, ECSDI.ProductoPendiente))
                grafoEnviar.add((contentEnviar, ECSDI.Nombre, Literal(nombre, datatype=XSD.string)))
                grafoEnviar.add((contentEnviar, ECSDI.Peso, Literal(peso, datatype=XSD.float)))
                grafoEnviar.add((contentEnviar, ECSDI.Prioridad, Literal(prioritat, datatype=XSD.int)))

                grafoEnviar.add((direccion, RDF.type, ECSDI.Direccion))
                grafoEnviar.add((direccion, ECSDI.Direccion, Literal(direccion2, datatype=XSD.string)))
                grafoEnviar.add((direccion, ECSDI.CodigoPostal, Literal(codigopostal, datatype=XSD.int)))
                grafoEnviar.add((contentEnviar, ECSDI.EnviarA, URIRef(direccion)))

                grafoPendientes += grafoEnviar
                grafoPendientes.serialize(destination="../data/ProductosPendientesDB", format='turtle')

                # TODO baixar 1 el stock
    #thread1 = threading.Thread(target=crearLote, args=(grafoEnviar, contentEnviar))
    #thread1.start()

    return grafoFaltan


# Aixo servira per agafar els productes pendents i ordenar-los en lots
def crearLotes():
    graph = Graph()
    graphLotes = Graph()

    ontologyFile = open("../data/ProductosPendientesDB")
    graph.parse(ontologyFile, format='turtle')
    ontologyFile2 = open("../data/LotesPendientesDB")
    graphLotes.parse(ontologyFile2, format='turtle')

    for a,b,c in graph:
        print(a,b,c)

    graph_query = []

    nouLote = Graph()
    nouLote.bind('ECSDI', ECSDI)

    contentLote = ECSDI['LoteProductos' + str(getMessageCount())]
    nouLote.add((contentLote, RDF.type, ECSDI.LoteProductos))
    pesoLote = 0

    for producto_pendiente in graph.subjects(predicate=RDF.type, object=ECSDI.ProductoPendiente):
        print(graph.value(subject=producto_pendiente, predicate=ECSDI.Prioridad))
        if int(graph.value(subject=producto_pendiente, predicate=ECSDI.Prioridad)) == 1:
            print("Holi, soc dintre del IF")

            ## Agafem els atributs del producte pendent
            producto_direccion = graph.value(subject=producto_pendiente, predicate=ECSDI.EnviarA)
            producto_nombre = graph.value(subject=producto_pendiente, predicate=ECSDI.Nombre)
            peso = graph.value(subject=producto_pendiente, predicate=ECSDI.Peso)
            producto_adress = graph.value(subject=producto_direccion, predicate=ECSDI.Direccion)
            producto_codigo_postal = graph.value(subject=producto_direccion, predicate=ECSDI.CodigoPostal)

            ## Afegim el producte al graf nouLote
            nouLote.add((producto_pendiente, RDF.type, ECSDI.ProductoPendiente))
            nouLote.add((producto_pendiente, ECSDI.Nombre, Literal(producto_nombre, datatype=XSD.string)))
            nouLote.add((producto_direccion, RDF.type, ECSDI.Direccion))
            nouLote.add((producto_direccion, ECSDI.Direccion, Literal(producto_adress, datatype=XSD.string)))
            nouLote.add((producto_direccion, ECSDI.CodigoPostal, Literal(producto_codigo_postal, datatype=XSD.int)))
            nouLote.add((producto_pendiente, ECSDI.EnviarA, producto_direccion))
            nouLote.add((contentLote, ECSDI.CompuestoPor, producto_pendiente))

            pesoLote = peso + pesoLote
            print (pesoLote)

            for item in graph.objects(subject=producto_pendiente):
                graph.remove((producto_pendiente, None, item))

            for item in graph.objects(subject=producto_direccion):
                graph.remove((producto_direccion, None, item))

        else:
            print("Holi, soc dintre del ELSE")
            prioridad = int(graph.value(subject=producto_pendiente, predicate=ECSDI.Prioridad))
            prioridad = prioridad - 1
            graph.add((producto_pendiente, ECSDI.Prioridad, Literal(prioridad, datatype=XSD.int)))

    nouLote.add((contentLote, ECSDI.Peso, Literal(pesoLote, datatype=XSD.float)))

    print("nouLote")
    for a, b, c in nouLote:
        print(a, b, c)

    if pesoLote != 0:
        graphLotes += nouLote

    print("Lotes Pendientes")
    for a, b, c in graphLotes:
        print(a, b, c)

    graphLotes.serialize(destination="../data/LotesPendientesDB", format='turtle')
    graph.serialize(destination="../data/ProductosPendientesDB", format='turtle')

    return

def crearLotesThread():
    thread = threading.Thread(target=crearLotes)
    thread.start()
    thread.join()
    sleep(500)

    crearLotesThread()


@app.route("/Stop")
def stop():
    """
    Entrypoint to the agent
    :return: string
    """

    tidyUp()
    shutdown_server()
    return "Stopping server"


def tidyUp():
    """
    Previous actions for the agent.
    """

    global queue
    queue.put(0)

    pass

def centroLogistico1Behaviour(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    gr = register_message()


if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    thread = threading.Thread(target=crearLotesThread)
    thread.start()
    ab1 = Process(target=centroLogistico1Behaviour, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    thread.join()
    print('The End')