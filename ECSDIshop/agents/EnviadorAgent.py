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
    port = 9004
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
EnviadorAgent = Agent('EnviadorAgent',
                    agn.EnviadorAgent,
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

    resultadoComunicacion = Graph()

    if messageProperties is None:
        # Respondemos que no hemos entendido el mensaje
        resultadoComunicacion = build_message(Graph(), ACL['not-understood'],
                                              sender=EnviadorAgent.uri, msgcnt=getMessageCount())
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
            # Si la acción es de tipo peticiónCompra emprendemos las acciones consequentes
            if accion == ECSDI.PeticionCompra:
                logger.info("Procesando peticion de compra")
                # Eliminar los ACLMessage
                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))

                procesarCompra(grafoEntrada,content)

    #no retronamso nada
    logger.info('Respondemos a la petición de venta')
    serialize = resultadoComunicacion.serialize(format='xml')
    return serialize, 200

def procesarCompra(grafo,contenido):
    thread1 = threading.Thread(target=registrarCompra,args=(grafo,))
    thread1.start()
    thread2 = threading.Thread(target=solicitarEnvio,args=(grafo,contenido))
    thread2.start()

def solicitarEnvio(grafo,contenido):
    direccion = grafo.subjects(object=ECSDI.Direccion)
    codigoPostal = None
    for d in direccion:
        codigoPostal = grafo.value(subject=d,predicate=ECSDI.CodigoPostal)
    centroLogisticoAgente = getAgentInfo(agn.CentroLogisticoDirectoryAgent, DirectoryAgent, EnviadorAgent, getMessageCount())
    prioridad = grafo.value(subject=contenido,predicate=ECSDI.Prioridad)
    if codigoPostal != None:
        agentes = getCentroLogisticoPorProximidad(agn.CentroLogisticoAgent, centroLogisticoAgente, EnviadorAgent, getMessageCount(), codigoPostal)
        peticionEnvio = Graph()
        peticionEnvio.bind('ECSDI', ECSDI)
        contenido = ECSDI['PeticionEnvioACentroLogistico' + str(getMessageCount())]
        peticionEnvio.add((contenido, RDF.type, ECSDI.PeticionEnvioACentroLogistico))
        peticionEnvio.add((contenido,ECSDI.Prioridad,Literal(prioridad,datatype=XSD.int)))



        for a,b,c in peticionEnvio:
            print(a,b,c)

        for a in agentes:
            logger.info("Solicitando peticion de envio a centro logistico")
            respuesta = send_message(
                build_message(peticionEnvio, perf=ACL.request, sender=EnviadorAgent.uri, receiver=a.uri,
                              msgcnt=getMessageCount(),
                              content=contenido), a.address)


def registrarCompra(grafo):
    compra = grafo.value(predicate=RDF.type,object=ECSDI.PeticionCompra)
    grafo.add((compra,ECSDI.Pagado,Literal(False,datatype=XSD.boolean)))
    logger.info("Registrando la compra")
    ontologyFile = open('../data/ComprasDB')

    grafoCompras = Graph()
    grafoCompras.parse(ontologyFile, format='turtle')
    grafoCompras += grafo

    # Guardem el graf
    grafoCompras.serialize(destination='../data/ComprasDB', format='turtle')

@app.route("/Stop")
def stop():
    """
    Entrypoint to the agent
    :return: string
    """

    tidyUp()
    shutdown_server()
    return "Stopping server"

#funcion llamada al principio de un agente
def enviadorBehavior(queue):

    """
    Agent Behaviour in a concurrent thread.
    :param queue: the queue
    :return: something
    """
    gr = register_message()

#función llamada antes de cerrar el servidor
def tidyUp():
    """
    Previous actions for the agent.
    """

    global queue
    queue.put(0)

    pass

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

    gr = registerAgent(EnviadorAgent, DirectoryAgent, EnviadorAgent.uri, getMessageCount())
    return gr

def comprobarYCobrar():
    logger.info("Realizando cobros rutinarios")
    ontologyFile = open('../data/ComprasDB')

    grafoCompras = Graph()
    grafoCompras.parse(ontologyFile, format='turtle')
    compras = grafoCompras.subjects(object=ECSDI.PeticionCompra)
    for compra in compras:
        pagado = grafoCompras.value(subject=compra,predicate=ECSDI.Pagado)
        if not pagado:
            pedirCobro(grafoCompras.value(subject=compra,predicate=ECSDI.Tarjeta),
                       grafoCompras.value(subject=compra,predicate=ECSDI.PrecioTotal))
            grafoCompras.remove((compra,ECSDI.Pagado,None))
            grafoCompras.add((compra,ECSDI.Pagado,Literal(True,datatype=XSD.boolean)))
            grafoCompras.serialize(destination='../data/ComprasDB', format='turtle')


    return

def pedirCobro(tarjeta,cantidad):
    peticion = Graph()
    peticion.bind('ECSDI',ECSDI)
    sujeto = ECSDI['PeticionTransferencia'+str(getMessageCount())]
    peticion.add((sujeto,RDF.type,ECSDI.PeticionTransferencia))
    peticion.add((sujeto,ECSDI.Tarjeta,Literal(tarjeta,datatype=XSD.int)))
    peticion.add((sujeto,ECSDI.PrecioTotal,Literal(cantidad,datatype=XSD.float)))
    logger.info("Solicitando cobro")
    agenteCobrador = getAgentInfo(agn.TesoreroAgent,DirectoryAgent,EnviadorAgent,getMessageCount())
    if agenteCobrador is not None:
        resultado = send_message(build_message(peticion,perf=ACL.request, sender=EnviadorAgent.uri,receiver=agenteCobrador.uri,
                               msgcnt=getMessageCount(),content=sujeto),agenteCobrador.address)
    return

def cobrar():
    thread = threading.Thread(target=comprobarYCobrar)
    thread.start()
    thread.join()
    sleep(10)

    cobrar()



if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    thread = threading.Thread(target=cobrar)
    thread.start()
    ab1 = Process(target=enviadorBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    thread.join()

    print('The End')