"""
Cliente para enviar documentos DTE mediante Softland
"""

import base64
import json
import re
import datetime
from typing import List
from pydantic import BaseModel, PositiveInt, Field
from zeep import Client

regex_variables = r"(\$[a-z_]+)"

class DocumentItem(BaseModel):
    # Item despachado
    item_codigo: str
    item_detalle: str
    item_descripcion: str
    item_cantidad: int

class DocumentData(BaseModel):
    bodega_origen: str  # 01
    folio: PositiveInt = Field(
        gt=0, lt=99999999
    )  # 8 caracteres, podria ser AÑO + Minutos desde el 01/01
    fecha: str  # dd-mm-AAAA
    observacion: str  # Obervación

    # Cliente
    cliente_codigo: str
    cliente_nombre: str
    cliente_rut: str
    cliente_giro: str
    cliente_direccion: str
    cliente_comuna: str
    cliente_provincia: str

    # Destino
    lugar_despacho_codigo: str
    lugar_despacho_direccion: str
    lugar_despacho_comuna: str
    lugar_despacho_provincia: str
    items: List[DocumentItem]

    def to_csv(self, template_base_string: str) -> str:
        """Remplazamos cada variable en la string y copiamos las lineas X veces segun cantidad de items"""
        """ La segunda linea es nuestra linea con variables """
        linea_variable = template_base_string.splitlines()[1]
        item_count = len(self.items)

        lineas_pobladas = []
        for i in range(0, item_count, 1):
            """Por cada item, copiamos la linea y remplazamos"""
            linea_poblada = self.replace_in_string(
                format_string=linea_variable, item_index=i
            )
            lineas_pobladas.append(linea_poblada)

        """ Concatenamos con salto de linea """
        SALTO_DE_LINEA = "\r\n"
        full_doc = (
            template_base_string.splitlines()[0]
            + SALTO_DE_LINEA
            + SALTO_DE_LINEA.join(lineas_pobladas)
        )

        return full_doc

    def replace_in_string(self, format_string: str, item_index: int) -> str:
        """Remplazamos las variables que tengan prefijo $"""
        matches = re.finditer(regex_variables, format_string)
        for match in matches:
            """Por cada match, recuperamos el nombre de la variable sin $ y remplacemos por su valor"""
            nombre_variable = match.group()
            nombre_atributo = nombre_variable.replace("$", "")

            if nombre_atributo.startswith("item_"):
                """Es un item"""
                current_item = self.items[item_index]
                nuevo_valor = getattr(current_item, nombre_atributo)
            else:
                """Valor definido"""
                nuevo_valor = getattr(self, nombre_atributo)
            format_string = format_string.replace(nombre_variable, str(nuevo_valor))
        return format_string


def generate_folio() -> int:
    """Generamos un folio con el prefijo del año y la cantidad de minutos desde el 01/01 del año"""
    """ Minutos por año: 525600"""
    """ Ejemplo: 24525600 => 31/12/2024 23:59:00 """
    fecha_actual = datetime.datetime.now()
    primer_dia_del_ano = datetime.datetime(fecha_actual.year, 1, 1)
    segundos_diff = (fecha_actual - primer_dia_del_ano).total_seconds() / 60.0
    return str(fecha_actual.year)[-2:] + str(round(segundos_diff))


def template_to_base64(document_data: DocumentData):
    with open("./template/envio_variable.csv", "r", encoding="utf-8") as image_file:
        """Leemos el template"""
        variable_string = image_file.read()
        """ Remplazamos con las variables """
        documento_listo = document_data.to_csv(variable_string)

        encoded_string = base64.b64encode(documento_listo.encode("utf-8"))
        return encoded_string


def base64_to_pdf(pdfb64):
    file_bytes = base64.b64decode(pdfb64, validate=True)
    if file_bytes[0:4] != b"%PDF":
        raise ValueError("Firma PDF incorrecta")

    return file_bytes

def send_to_softland(
    document_data: DocumentData,
    wsdl_url: str,
    areaDeDatos: str,
    usuario: str,
    nombreCertificadoDigital: str,
):
    client = Client(wsdl_url)
    base64File = template_to_base64(document_data)
    result = client.service.CaptudaGuiaSalida(
        base64File=base64File,
        extensionArchivo="txt",
        areaDeDatos=areaDeDatos,
        usuario=usuario,
        nombreCertificadoDigital=nombreCertificadoDigital,
    )
    """ Hay un resultado """
    assert result
    folio = result["FolioDte"]
    pdfb64 = result["PdfenBase64"]
    if pdfb64:
        """ Devolvemos el folio y el PDF en base 64 como conjunto de bytes """
        return folio, base64_to_pdf(pdfb64)
    else:
        raise AssertionError(result["Error"])


def test_envio(
    wsdl_url: str,
    areaDeDatos: str,
    usuario: str,
    nombreCertificadoDigital: str,
):
    documento_prueba = {
        "bodega_origen": "01",
        "folio": generate_folio(),
        "fecha": datetime.datetime.now().strftime("%d-%m-%Y"),
        "observacion": "Pruba de emision desde DaiaERP",
        "cliente_codigo": "DAIA",
        "cliente_nombre": "DAIA SYSTEMS SPA",
        "cliente_rut": "1111111-1",
        "cliente_giro": "EDICIÓN DE PROGAMAS INFORMATICOS",
        "cliente_direccion": "CARMEN 487, OF 301, CURICO",
        "cliente_comuna": "CURICO",
        "cliente_provincia": "CURICO",
        "lugar_despacho_codigo": "DAI",
        "lugar_despacho_direccion": "CARMEN 487, OF 301, CURICO",
        "lugar_despacho_comuna": "CURICO",
        "lugar_despacho_provincia": "CURICO",
        "items": [
            {
                "item_codigo": "P01",
                "item_detalle": "PRUEBA 01",
                "item_descripcion": "PRUEBA 01",
                "item_cantidad": 1,
            },
            {
                "item_codigo": "P02",
                "item_detalle": "PRUEBA 02",
                "item_descripcion": "PRUEBA 02",
                "item_cantidad": 2,
            },
        ],
    }
    mocked_json = json.loads(json.dumps(documento_prueba))
    mocked = DocumentData(**mocked_json)
    try:
        folio, base64PdfBytes = send_to_softland(mocked, wsdl_url, areaDeDatos, usuario, nombreCertificadoDigital)
        """ Escribir el PDF y mostrar el folio  """
        print("Folio enviado " + str(folio))
        with open("file.pdf", "wb") as f:
            return f.write(base64PdfBytes)
    except AssertionError as ae:
        print(ae)
