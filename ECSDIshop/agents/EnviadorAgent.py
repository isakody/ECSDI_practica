# -*- coding: utf-8 -*-

"""
Agente usando los servicios web de Flask
/comm es la entrada para la recepcion de mensajes del agente
/Stop es la entrada que para el agente
Tiene una funcion AgentBehavior1 que se lanza como un thread concurrente
Asume que el agente de registro esta en el puerto 9000
"""
import argparse
import copy
import socket
import sys
import threading
from multiprocessing import Queue, Process
from time import sleep
from datetime import datetime, timedelta

from flask import Flask, request
from rdflib import URIRef, XSD, RDF

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

#función incremental de numero de mensajes
def getMessageCount():
    global mss_cnt
    mss_cnt += 1
    return mss_cnt

def procesarEnvio(grafo, contenido):
    logger.info("Recibida peticion de envio")
    thread1 = threading.Thread(target=registrarEnvio,args=(grafo,contenido))
    thread1.start()
    thread2 = threading.Thread(target=solicitarEnvio,args=(grafo,contenido))
    thread2.start()

def solicitarEnvio(grafo,contenido):
    grafoCopia = grafo
    grafoCopia.bind('default', ECSDI)
    direccion = grafo.subjects(object=ECSDI.Direccion)
    codigoPostal = None
    logger.info("Haciendo peticion envio a Centro Logistico")
    for d in direccion:
        codigoPostal = grafo.value(subject=d,predicate=ECSDI.CodigoPostal)
    centroLogisticoAgente = getAgentInfo(agn.CentroLogisticoDirectoryAgent, DirectoryAgent, EnviadorAgent, getMessageCount())
    prioridad = grafo.value(subject=contenido,predicate=ECSDI.Prioridad)
    # solicitamos centros logisticos dependiendo del codigo postal
    if codigoPostal is not None:
        agentes = getCentroLogisticoPorProximidad(agn.CentroLogisticoAgent, centroLogisticoAgente, EnviadorAgent, getMessageCount(), int(codigoPostal))


        grafoCopia.remove((contenido,ECSDI.Tarjeta,None))
        grafoCopia.remove((contenido,RDF.type,ECSDI.PeticionEnvio))
        sujeto = ECSDI['PeticionEnvioACentroLogistico' + str(getMessageCount())]
        grafoCopia.add((sujeto, RDF.type, ECSDI.PeticionEnvioACentroLogistico))

        for a, b, c in grafoCopia:
            if a == contenido:
                if b == ECSDI.De: #Compra
                    grafoCopia.remove((a, b, c))
                    grafoCopia.add((sujeto, ECSDI.EnvioDe, c))
                else:
                    grafoCopia.remove((a,b,c))
                    grafoCopia.add((sujeto,b,c))

        for ag in agentes:
            logger.info("Enviando peticion envio a Centro Logistico")
            respuesta = send_message(
                build_message(grafoCopia, perf=ACL.request, sender=EnviadorAgent.uri, receiver=ag.uri,
                              msgcnt=getMessageCount(),
                              content=sujeto), ag.address)
            logger.info("Recibida respuesta de envio a Centro Logistico")
            accion = respuesta.subjects(predicate=RDF.type, object=ECSDI.RespuestaEnvioDesdeCentroLogistico)
            contenido = None
            for a in accion:
                contenido = a

            for item in respuesta.subjects(RDF.type, ACL.FipaAclMessage):
                respuesta.remove((item, None, None))
            respuesta.remove((None, RDF.type, ECSDI.RespuestaEnvioDesdeCentroLogistico))
            respuesta.add((sujeto, RDF.type, ECSDI.PeticionEnvioACentroLogistico))

            grafoCopia = respuesta

            contiene = False
            for a, b, c in grafoCopia:
                if a == contenido:
                    if b == ECSDI.Faltan:  # Compra
                        grafoCopia.remove((a, b, c))
                        grafoCopia.add((sujeto, ECSDI.EnvioDe, c))

                    elif b == ECSDI.Contiene:
                        contiene = True
                    else:
                        grafoCopia.remove((a, b, c))
                        grafoCopia.add((sujeto, b, c))

            if not contiene:
                break
            else:
                logger.info("Faltan productos por enviar. Probamos con otro centro logístico")
    logger.info("Enviada peticion envio a Centro Logistico")


def registrarEnvio(grafo, contenido):

    envio = grafo.value(predicate=RDF.type,object=ECSDI.PeticionEnvio)
    grafo.add((envio,ECSDI.Pagado,Literal(False,datatype=XSD.boolean)))
    prioridad = grafo.value(subject=contenido, predicate=ECSDI.Prioridad)
    fecha = datetime.now() + timedelta(days=int(prioridad))
    grafo.add((envio,ECSDI.FechaEntrega,Literal(fecha, datatype=XSD.date)))
    logger.info("Registrando el envio")
    ontologyFile = open('../data/EnviosDB')

    grafoEnvios = Graph()
    grafoEnvios.bind('default', ECSDI)
    grafoEnvios.parse(ontologyFile, format='turtle')
    grafoEnvios += grafo

    # Guardem el graf
    grafoEnvios.serialize(destination='../data/EnviosDB', format='turtle')
    logger.info("Registro de envio finalizado")

# Funciones eliminadas al no implementar el tesorero
"""def comprobarYCobrar():
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

    cobrar()"""



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
            if accion == ECSDI.PeticionEnvio:
                logger.info("Procesando peticion de envio")
                # Eliminar los ACLMessage
                for item in grafoEntrada.subjects(RDF.type, ACL.FipaAclMessage):
                    grafoEntrada.remove((item, None, None))

                procesarEnvio(grafoEntrada, content)

    logger.info('Respondemos a la petición de venta')
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

if __name__ == '__main__':
    # ------------------------------------------------------------------------------------------------------
    # Run behaviors
    """thread = threading.Thread(target=cobrar)
    #thread.start()"""
    ab1 = Process(target=enviadorBehavior, args=(queue,))
    ab1.start()

    # Run server
    app.run(host=hostname, port=port, debug=False)

    # Wait behaviors
    ab1.join()
    #thread.join()

    print('The End')