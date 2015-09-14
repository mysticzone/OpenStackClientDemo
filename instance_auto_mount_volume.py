#!/usr/bin/env python
# coding:utf-8

from cinderclient import client as cinderclient
from glanceclient import Client as glanceclient
from keystoneclient.auth.identity import v2
from keystoneclient import session
from novaclient import client as novaclient

import time
import os
import paramiko
import socket

AUTH_URL = "http://200.21.4.45:5000/v2.0"
USERNAME = "admin"
PASSWORD = "yanghaosysadmin"
PROJECT_NAME = "admin"

auth = v2.Password(auth_url=AUTH_URL,
                   username=USERNAME,
                   password=PASSWORD,
                   tenant_name=PROJECT_NAME)
sess = session.Session(auth=auth)
nova = novaclient.Client("2", session=sess)

OS_IMAGE_ENDPOINT = auth.get_endpoint(sess, interface="public", service_type="image")
OS_AUTH_TOKEN = auth.get_token(sess)

# Glance Identity
glance = glanceclient('2', endpoint=OS_IMAGE_ENDPOINT, token=OS_AUTH_TOKEN)

# Cinder Identity
cinder = cinderclient.Client("2",
                             USERNAME,
                             PASSWORD,
                             PROJECT_NAME,
                             AUTH_URL)

# Time Out
TIMEOUT = 120

# Instance Name
VM_NAME = "test1"

# Define Flavor
FLAVOR_NAME = "2U2G20"
FLAVOR_MEM = 2048
FLAVOR_CPU = 2
FLAVOR_DISK = 20

# Image Information
IMAGE_NAME = "Test Image"
IMAGE_PATH = "/home/stack/trusty-server-cloudimg-amd64-disk1.img"

# Define Volume
VOLUME_SIZE = 2
VOLUME_NAME = "test-vol"

## Generate keyparis
KEY_NAME_PUB = "cloud_pub_key"
KEY_NAME_PRI = "cloud_pri_key"

# Define command
COMM_MOUNT = "sudo mkfs.ext4 /dev/vdb"
COMM_FORMAT = "sudo mount /dev/vdb /mnt"

def get_network_id():
    networks = nova.networks.list()
    network_id = networks[0].id
    return network_id

def create_volume():
    volume = cinder.volumes.create(name=VOLUME_NAME, size=VOLUME_SIZE)
    volume_id = volume.id

    print "The volume %s has been created!" % (volume.name)
    return volume_id

def delete_volume():
    volumes = cinder.volumes.list()
    for volume in volumes:
        if volume.name == VOLUME_NAME:
            cinder.volumes.delete(volume.id)
            print "The volume %s has been deleted successfully!" % (volume.name)

def create_flavor():
    flavor = nova.flavors.create(FLAVOR_NAME,
                                 FLAVOR_MEM,
                                 FLAVOR_CPU,
                                 FLAVOR_DISK)
    print "The flavor %s has been created!" % flavor.name
    return flavor.id

def delete_flavor():
    flavors = nova.flavors.list()
    for flavor in flavors:
        if flavor.name == FLAVOR_NAME:
            nova.flavors.delete(flavor.id)
            print "The flavor %s has been deleted!" % flavor.name

def create_instance():
    instance_id = None
    # Create flavor
    flavor_id = create_flavor()
    # Upload image
    image_id = upload_image()
    # Create vm
    instance = nova.servers.create(VM_NAME,
                                       image_id,
                                       flavor_id,
                                       key_name=KEY_NAME_PUB,
                                       nics=[{'net-id': get_network_id()}])

    print "The instance %s has been created!" % (instance.id)
    return instance.id

def delete_instance():
    instance_id = None
    vms = nova.servers.list()

    # Delete the instance
    for vm in vms:
        if vm.name == VM_NAME:
            instance_id = vm.id
            nova.servers.delete(vm.id)
            print "The instance %s will be deleted!" % (vm.name)

    return instance_id

def create_keypair():
    keypairs = nova.keypairs.create(KEY_NAME_PUB)
    fp = os.open(KEY_NAME_PRI, os.O_WRONLY | os.O_CREAT, 0o600)

    with os.fdopen(fp, 'w') as f:
             f.write(keypairs.private_key)
    print "The %s has been created!" % (KEY_NAME_PUB)

def delete_keypair():
    keys = nova.keypairs.list()
    for key in keys:
        if key.name == KEY_NAME_PUB:
            nova.keypairs.delete(key.id)
            print "The %s have been deleted!" % (KEY_NAME_PUB)

def upload_image():
    image = glance.images.create(name=IMAGE_NAME,
                                 disk_format="qcow2",
                                 container_format="bare",
                                 visibility="public")

    glance.images.upload(image.id, open(IMAGE_PATH, "rb"))
    print "The image %s has been uploaded!" % IMAGE_PATH.split("/")[3]
    return image.id

def delete_image():
    images = glance.images.list()
    try:
        while True:
            image = images.next()
            if image["name"] == IMAGE_NAME:
                glance.images.delete(image["id"])
                print "The image %s has been deleted!" % (IMAGE_NAME)
                break
    except StopIteration:
        print "Delete Image Occur Error!"

def mount_volume_to_instance(instance, volume):
    nova.volumes.create_server_volume(instance, volume, "/dev/vdb")
    print "The volume %s has mount to instance %s!" % (VOLUME_NAME, VM_NAME)

def allocate_fip_to_instance(instance):
    fip = nova.floating_ips.create(pool="public")
    nova.servers.add_floating_ip(instance, fip.ip)
    print "The %s has been allocated to the instance!" % (fip.ip)
    return fip.ip

def format_mount_volume(fip):

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ## Modified exception handling
    while True:
        try:
            ssh.connect(fip, username="ubuntu", key_filename=KEY_NAME_PRI)
            print "Connecting Successfully!"
            break
        except socket.error,e:
            print "Connection Failed because %s!!!!" % e
            time.sleep(1)
            continue

    ## More information output
    stdin, stdout, stderr = ssh.exec_command(COMM_MOUNT)
    print stdout.read()
    ssh.exec_command(COMM_FORMAT)


def clean_all():
    """ All Clean Resource"""
    # Delete vm
    instance_id = delete_instance()
    # Delete flavor
    delete_flavor()

    # Drop image
    delete_image()
    # Delete keypair
    delete_keypair()

    # Delete floating_ips
    fips = nova.floating_ips.list()
    for fip in fips:
        if fip.instance_id == instance_id:
            nova.floating_ips.delete(fip.id)
            print "Floating ip %s has been deleted!" % (fip.ip)

    # Waiting instance to be deleted
    for count in xrange(0, TIMEOUT):
        time.sleep(1)
        try:
            vm_state = nova.servers.get(instance_id)
        except Exception:
            vm_state = None

        if vm_state is None:
            print "The instance has been deleted!"
            break
        else:
            print "Waiting for the instance to be deleted!"
    else:
        print "Instance %s delete fails!!!!" % vm_state.name

    # Delete volume
    delete_volume()

def main():
    print "All clean everthing...."
    clean_all()

    # Generate keypairs
    create_keypair()

    # Create instance
    instance_id = create_instance()

    # Create volume
    volume_id = create_volume()

    # Check instance status
    for count in xrange(0, TIMEOUT):
        time.sleep(1)
        vm = nova.servers.get(instance_id)
        if vm.status == "ACTIVE":
            print "The current state of the instance is OK!"
            break
        else:
            print "The current state of the instance is %s" % (vm.status)
    else:
        print "The instance %s status is currently UNAVAILABLE!!!!" % (vm.name)

    # Allocate floating ip to instance
    floating_ip = allocate_fip_to_instance(instance_id)

    # Check volume status
    for count in xrange(0, TIMEOUT):
        time.sleep(1)
        vol = cinder.volumes.get(volume_id)
        if vol.status == "available":
            print "The current state of the volume is OK!"
            break
        else:
            print "The current state of the volume is %s" % (vol.status)
    else:
        print "The volume %s status is currently UNAVAILABLE!!!!" % (vol.name)

    # Attach volume to instance
    if vm.status == "ACTIVE" and vol.status == "available":
        mount_volume_to_instance(instance_id, volume_id)

    # Detection mounted volume status
    for count in xrange(0, TIMEOUT):
        time.sleep(1)
        vol = nova.volumes.get(volume_id)
        if vol.status == "in-use":
            print "The volume has been mounted!"

            # Format and mount volume
            format_mount_volume(floating_ip)

            break
        else:
            print "The current state of the volume mount is %s!" % (vol.status)
    else:
        print "The volume %s mount FAILs!!!!" % (vol.name)


if __name__=="__main__":
    main()

