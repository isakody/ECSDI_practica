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
from multiprocessing import Queue, Process

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
    port = 9002
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
FilterAgent = Agent('SellerAgent',
                    agn.FilterAgent,
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

#funcion llamada en /comm
@app.route("/comm")
def communication():
    message = request.args['content']
    grafoEntrada = Graph()
    grafoEntrada.parse(data=message)

    messageProperties = get_message_properties(grafoEntrada)

    resultadoComunicacion = None

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=FilterAgent.uri, msgcnt=getMessageCount())
    else:
        # Obtenemos la performativa
        if messageProperties['performative'] != ACL.request:
            # Si no es un request, respondemos que no hemos entendido el mensaje
            resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                                  sender=DirectoryAgent.uri, msgcnt=getMessageCount())
        else:
            # Extraemos el contenido que ha de ser una accion de la ontologia definida en Protege
            content = messageProperties['content']
            accion = grafoEntrada.value(subject=content, predicate=RDF.type)

            # Si la acción es de tipo busqueda emprendemos las acciones consequentes
            if accion == ECSDI.BuscarProducto:
                # Extraemos las restricciones de busqueda que se nos pasan y creamos un contenedor de las restriciones
                # para su posterior procesamiento
                restricciones = grafoEntrada.objects(content, ECSDI.RestringidaPor)
                directivasRestrictivas = {}
                for restriccion in restricciones:
                    if grafoEntrada.value(subject=restriccion, predicate=RDF.type) == ECSDI.RestriccionDeNombre:
                        nombre = grafoEntrada.value(subject=restriccion, predicate=ECSDI.Nombre)
                        directivasRestrictivas['Nombre'] = nombre
                    elif grafoEntrada.value(subject=restriccion, predicate=RDF.type) == ECSDI.RestriccionDePrecio:
                        precioMax = grafoEntrada.value(subject=restriccion, predicate=ECSDI.PrecioMaximo)
                        precioMin = grafoEntrada.value(subject=restriccion, predicate=ECSDI.PrecioMinimo)
                        directivasRestrictivas['PrecioMax'] = precioMax
                        directivasRestrictivas['PrecioMin'] = precioMin

                # Llamamos a una funcion que nos retorna un grafo con la información acorde al filtro establecido por el usuario
                resultadoComunicacion = findProductsByFilter(**directivasRestrictivas)

            logger.info('Respondemos a la petición de busqueda')
            serialize = resultadoComunicacion.serialize(format='xml')
            return serialize, 200

@app.route("/Stop")
def stop():
    """
    Entrypoint to the agent
    :return: string
    """

    tidyUp()
    shutdown_server()
    return "Stopping server"

#función para registro de agente en el servicio de directorios
def register_message():
    """
    Envia un mensaje de registro al servicio de registro
    usando una performativa Request y una accion Register del
    servicio de directorio

    :param gmess:
    :return:
    """

    logger.info('Nos registramos')

    gr = registerAgent(FilterAgent, DirectoryAgent, FilterAgent.uri, getMessageCount())
    return gr

#función llamada antes de cerrar el servidor
def tidyUp():
    """
    Previous actions for the agent.
    """

    global queue
    queue.put(0)

    pass

#funcion llamada al principio de un agente
def filterBehavior(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    gr = register_message()

# TODO implementar este metodo y base de datos tipo RDF acorde a la ontologia de Protege
# Función que busca productos en la base de datos acorde a los filtros establecidos con anterioriad
def findProductsByFilter(Nombre=None,PrecioMin=0.0,PrecioMax=sys.float_info.max):
    graph = Graph()
    ontologyFile = open('../data/ProductsDB.owl')
    graph.parse(ontologyFile, format='turtle')

    addAnd = False;

    query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX default: <http://www.owl-ontologies.com/ECSDIstore#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?Producto ?Nombre ?Precio ?Descripcion ?Id
    where {
        ?Producto rdf:type default:Producto .
        ?Producto default:Nombre ?Nombre .
        ?Producto default:Precio ?Precio .
        ?Producto default:Descripcion ?Descripcion .
        ?Producto default:Id ?Id .
        FILTER("""

    if Nombre is not None:
        query += """?Nombre = '""" + Nombre + """'"""
        addAnd = True



    if PrecioMin is not None:
        if addAnd:
            query += """ && """
            addAnd = False
        query += """?Precio >= """ + str(PrecioMin)
        addAnd = True


    if PrecioMax is not None:
        if addAnd:
            query += """ && """
            addAnd = False
        query += """?Precio <= """ + str(PrecioMax)

    query += """)}"""

    graph_query = graph.query(query)
    products_graph = Graph();
    products_graph.bind('ECSDI', ECSDI)
    for product in graph_query:
        product_nombre = product.Nombre
        product_precio = product.Precio
        product_descripcion = product.Descripcion
        print(product_nombre)
        print(product_precio)
        print(product_descripcion)
        sujeto = product.Producto
        products_graph.add((sujeto, RDF.type, ECSDI.Producto))
        products_graph.add((sujeto, ECSDI.Nombre, Literal(product_nombre, datatype=XSD.string)))
        products_graph.add((sujeto, ECSDI.Precio, Literal(product_precio, datatype=XSD.float)))
        products_graph.add((sujeto, ECSDI.Descripcion, Literal(product_descripcion, datatype=XSD.string)))

    return products_graph

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    ab1 = Process(target=filterBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=True)

    # Wait behaviors
    ab1.join()
    print('The End')