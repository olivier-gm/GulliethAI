# -*- coding: utf-8 -*-
"""Finaliza un documento usando LibreOffice a través de UNO.

Este script NO se ejecuta con el intérprete del proyecto: se lanza con el
Python que trae LibreOffice (el único que tiene el módulo `uno`), desde
`Document_process.convert()`.

Hace dos cosas que `soffice --convert-to pdf` no puede hacer:

  1. Actualiza la tabla de contenido (índice) para que quede con sus
     entradas y números de página reales. LibreOffice no actualiza los
     índices al cargar, ni con <w:updateFields> ni con w:dirty, así que hay
     que pedírselo explícitamente con XDocumentIndex.update().
  2. Guarda el .docx ya con el índice poblado y exporta el .pdf desde ese
     mismo documento en memoria, de modo que ambos formatos salgan con el
     índice hecho y el usuario no tenga que pulsar nada en Word.

Uso:
    <lo_python> lo_finalize.py <ruta.docx> <ruta_salida.pdf> [ruta_soffice]
"""
import os
import sys

import uno            # noqa: F401  (necesario para inicializar el puente UNO)
import unohelper
import officehelper
from com.sun.star.beans import PropertyValue


def _pv(name, value):
    prop = PropertyValue()
    prop.Name = name
    prop.Value = value
    return prop


def main():
    if len(sys.argv) < 3:
        print('uso: lo_finalize.py <docx> <pdf>', file=sys.stderr)
        return 2

    docx_path = os.path.abspath(sys.argv[1])
    pdf_path = os.path.abspath(sys.argv[2])

    if not os.path.isfile(docx_path):
        print('no existe el docx: %s' % docx_path, file=sys.stderr)
        return 2

    # Se le pasa la ruta exacta de soffice cuando el llamador la conoce:
    # officehelper por defecto lo busca en el PATH y ahí normalmente no está.
    #
    # Ojo: officehelper arma el comando con ' '.join(...) y sólo entrecomilla
    # la ruta que construye él mismo, no la que se le pasa por parámetro. Como
    # en Windows vive en "C:\Program Files\...", hay que entrecomillarla aquí
    # o el shell corta el comando en el primer espacio.
    soffice = sys.argv[3] if len(sys.argv) > 3 else None
    if soffice:
        if sys.platform.startswith('win'):
            if not soffice.startswith('"'):
                soffice = '"' + soffice + '"'
        else:
            import shlex
            soffice = shlex.quote(soffice)
        ctx = officehelper.bootstrap(soffice=soffice)
    else:
        ctx = officehelper.bootstrap()

    desktop = ctx.ServiceManager.createInstanceWithContext(
        'com.sun.star.frame.Desktop', ctx)

    doc = None
    try:
        doc = desktop.loadComponentFromURL(
            unohelper.systemPathToFileUrl(docx_path), '_blank', 0,
            (_pv('Hidden', True), _pv('ReadOnly', False)),
        )
        if doc is None:
            print('LibreOffice no pudo abrir el documento', file=sys.stderr)
            return 1

        # 1) Refrescar campos y poblar el índice
        try:
            doc.getTextFields().refresh()
        except Exception as e:
            print('aviso: no se pudieron refrescar los campos: %s' % e, file=sys.stderr)

        indexes = doc.getDocumentIndexes()
        for i in range(indexes.getCount()):
            indexes.getByIndex(i).update()
        print('indices actualizados: %d' % indexes.getCount())

        # 2) Guardar el docx ya con el índice poblado
        doc.storeToURL(
            unohelper.systemPathToFileUrl(docx_path),
            (_pv('FilterName', 'MS Word 2007 XML'), _pv('Overwrite', True)),
        )

        # 3) Exportar el PDF desde el mismo documento
        doc.storeToURL(
            unohelper.systemPathToFileUrl(pdf_path),
            (_pv('FilterName', 'writer_pdf_Export'), _pv('Overwrite', True)),
        )
        print('pdf generado: %s' % pdf_path)
        return 0
    finally:
        if doc is not None:
            try:
                doc.close(False)
            except Exception:
                pass
        try:
            desktop.terminate()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
