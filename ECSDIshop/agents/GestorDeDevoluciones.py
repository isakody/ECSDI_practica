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
import thread
import threading
from multiprocessing import Queue, Process
from random import randint
from time import sleep
from datetime import datetime, timedelta

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
    port = 9042
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
GestorDeDevolucionesAgent = Agent('GestorDeDevoluciones',
                    agn.GestorDeDevoluciones,
                    'http://%s:%d/comm' % (hostname, port),
                    'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:%d/Register' % (dhostname, dport),
                       'http://%s:%d/Stop' % (dhostname, dport))
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
    gr = registerAgent(GestorDeDevolucionesAgent, DirectoryAgent, GestorDeDevolucionesAgent.uri, getMessageCount())
    return gr

@app.route("/comm")
def communication():
    """
    Communication Entrypoint
    """
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)

    messageProperties = get_message_properties(grafoEntrada)

    resultadoComunicacion = None

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=GestorDeDevolucionesAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProperties['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                                  sender=DirectoryAgent.uri, msgcnt=getMessageCount())
        else:
            content = messageProperties['content']
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)
            # Si la acción es de tipo peticiónCompra emprendemos las acciones consequentes
            if accion == ECSDI.PeticionProductosComprados:
                graph = Graph()
                ontologyFile = open('../data/EnviosDB')
                tarjeta = None
                tarjetaObjects = grafoEntrada.objects(subject=content, predicate=ECSDI.Tarjeta)
                for t in tarjetaObjects:
                    tarjeta = t

                graph.parse(ontologyFile, format='turtle')
                query =  """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                            PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
                            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                            SELECT ?PeticionEnvio ?Producto ?Nombre ?Precio ?Descripcion ?Peso ?Tarjeta ?Compra ?FechaEntrega
                            where {
                                ?PeticionEnvio rdf:type default:PeticionEnvio .
                                ?PeticionEnvio default:Tarjeta ?Tarjeta .
                                ?PeticionEnvio default:De ?Compra .
                                ?PeticionEnvio default:FechaEntrega ?FechaEntrega .
                                ?Compra default:Contiene ?Producto .       
                                ?Producto default:Nombre ?Nombre .
                                ?Producto default:Precio ?Precio .
                                ?Producto default:Descripcion ?Descripcion .
                                ?Producto default:Peso ?Peso .
                                FILTER("""

                query += """?Tarjeta = """ + str(tarjeta)
                query += """ && ?FechaEntrega > '""" + str(datetime.now() - timedelta(days=15)) + """'^^xsd:date"""
                query += """)}"""


                resultadoConsulta = graph.query(query)
                resultadoComunicacion = Graph()


                for product in resultadoConsulta:
                    product_nombre = product.Nombre
                    product_precio = product.Precio
                    product_descripcion = product.Descripcion
                    product_peso = product.Peso
                    sujeto =  ECSDI['ProductoEnviado' + str(getMessageCount())]
                    resultadoComunicacion.add((sujeto, RDF.type, ECSDI.ProductoEnviado))
                    resultadoComunicacion.add((sujeto, ECSDI.Nombre, Literal(product_nombre, datatype=XSD.string)))
                    resultadoComunicacion.add((sujeto, ECSDI.Precio, Literal(product_precio, datatype=XSD.float)))
                    resultadoComunicacion.add((sujeto, ECSDI.Descripcion, Literal(product_descripcion, datatype=XSD.string)))
                    resultadoComunicacion.add((sujeto, ECSDI.Peso, Literal(product_peso, datatype=XSD.float)))
                    resultadoComunicacion.add((sujeto, ECSDI.EsDe, product.Compra))
            elif accion == ECSDI.RetornarProductos:
                direccion= grafoEntrada.objects(predicate=ECSDI.Direccion)
                direccionRetorno = None
                for d in direccion:
                    direccionRetorno = d
                codigo = grafoEntrada.objects(predicate=ECSDI.CodigoPostal)
                codigoPostal = None
                for c in codigo:
                    codigoPostal = c
                print(codigoPostal, direccionRetorno)
                thread1 = threading.Thread(target=solicitarEnvio,args=(direccionRetorno,codigoPostal))
                thread1.start()
                thread2 = threading.Thread(target=borrarProductosRetornados, args=(grafoEntrada,content))
                thread2.start()
                logger.info("Solicitando envio")
                resultadoComunicacion = Graph()

    logger.info('Respondemos a la petición de devolucion')
    serialize = resultadoComunicacion.serialize(format='xml')
    return serialize, 200

def borrarProductosRetornados(grafo, content):
    ontologyFile = open('../data/EnviosDB')

    products = grafo.objects(subject=content, predicate= ECSDI.Auna)
    print("entro")

    for a, b, c in grafo:
        print a, b, c

    grafoEnvios = Graph()
    grafoEnvios.bind('default', ECSDI)
    grafoEnvios.parse(ontologyFile, format='turtle')

    for product in products:
        print("entro2")
        print(product)
        compra = grafo.value(subject=product, predicate=ECSDI.EsDe)
        print(compra)
        nombre = grafo.value(subject=product, predicate=ECSDI.Nombre)
        print(nombre)

        query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?Producto ?Nombre  
            WHERE {  
                ?Producto rdf:type default:Producto . 
                ?Producto default:Nombre ?Nombre .
                FILTER("""

        query += """?Nombre = '""" + nombre + """'"""
        query += """)}"""

        graph_query = grafoEnvios.query(query)

        producto = None
        for p in graph_query:
            producto = p.Producto
        print(producto)

        grafoEnvios.remove((compra, None, producto))




    # Guardem el graf
    grafoEnvios.serialize(destination='../data/EnviosDB', format='turtle')

def solicitarEnvio(direccionRetorno,codigoPostal):
    #TODO pedir un transportista qualquiera y enviar la petición de recodiga
    logger.info("need to implement ask for transport")

    peticion = Graph()
    accion = ECSDI["PeticionRecodida"+str(getMessageCount())]
    peticion.add((accion,RDF.type,ECSDI.PeticionRecogida))
    sujetoDireccion = ECSDI['Direccion' + str(getMessageCount())]
    peticion.add((sujetoDireccion, RDF.type, ECSDI.Direccion))
    peticion.add((sujetoDireccion, ECSDI.Direccion, Literal(direccionRetorno, datatype=XSD.string)))
    peticion.add((sujetoDireccion, ECSDI.CodigoPostal, Literal(codigoPostal, datatype=XSD.int)))
    peticion.add((accion, ECSDI.Desde, URIRef(sujetoDireccion)))

    agente = getAgentInfo(agn.TransportistaDevolucionesAgent, DirectoryAgent, GestorDeDevolucionesAgent, getMessageCount())

    grafoBusqueda = send_message(
        build_message(peticion, perf=ACL.request, sender=GestorDeDevolucionesAgent.uri, receiver=agente.uri,
                      msgcnt=getMessageCount(),
                      content=accion), agente.address)

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

def DevolvedorBehaviour(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    gr = register_message()


if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=DevolvedorBehaviour, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    print('The End')