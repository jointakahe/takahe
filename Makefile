.PHONY: clean

image:
	docker build -t takahe -f docker/Dockerfile .

docs:
	cd docs/ && make html
