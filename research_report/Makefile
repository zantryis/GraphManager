LATEXMK ?= latexmk
MAIN_TEX := main.tex
MAIN_PDF := main.pdf

.PHONY: pdf clean

pdf:
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error $(MAIN_TEX)

clean:
	$(LATEXMK) -C
	rm -f $(MAIN_PDF)
