#include <linux/module.h> // for making a kernel module
#include <linux/gpio.h> // for interacting with GPIO pins
#include <linux/interrupt.h>  // for handling interrupts
#include <linux/fs.h> // for dev file stuff
#include <linux/cdev.h>
#include <linux/uaccess.h>

// Values of the GPIO pins and initialisation for variables


static bool	State = 0;

static unsigned int OffLed = 27;
static unsigned int GreenLed = 24;
static unsigned int YellowLed = 15;
static unsigned int RedLed = 4;

static unsigned int Button = 17;
static unsigned int Irqnum = 0;
static unsigned int Counter = 0;

unsigned int LastReportedValue = 0;
unsigned int Response = 0; // This could be a bool??

//buffer for the interaction between the user and the dev file
static char buffer[255];
static int pointer_to_buffer;

//things for creating the dev file
static dev_t device_number;
static struct class *device_class;
static struct cdev device_itself;

#define DRIVER_NAME "cloudLED"
#define DRIVER_CLASS "cloudLEDClass"

// Function for handling the dev file being opened
static int user_opened_the_file(struct inode *dev_file, struct file *instance)
{
	printk(KERN_INFO "The dev file has been opened!");
	return 0;
}

//Function for handling the dev file being closed
static int user_closed_the_file(struct inode *dev_file, struct file *instance)
{
	printk(KERN_INFO "The dev file has been closed!");
	return 0;
}

//Function for handling reads of the device file
static ssize_t user_read_the_file(struct file *dev_file, char *destination_buffer, size_t size_of_buffer, loff_t *offset)
{
	//We will be sending a value that can be represented by a bool, thus we can only write 1 byte of data to the file 
	// 1 - the cloud functionality should be triggered
	// 0 - the could functionality should not be triggered
	printk(KERN_INFO "The file has been read!");
	copy_to_user(destination_buffer,buffer,4); // we copy the data that we had to the user, we only care about copying a single byte of the data.

	//this seems a little bit hacky, todo: patch up later
	return 4; 
}

//Function for handling writes to the device file
static ssize_t user_wrote_the_file(struct file *dev_file, const char *source_buffer, size_t size_of_buffer, loff_t *offset)
{

	//as we only ever want to read a value between 0 and 100, we again can get away with operating with a single byte of data
	printk(KERN_INFO "The file has been written to!");
	copy_from_user(buffer,source_buffer,4);

	return 4;


}

// This struct maps the functions we wrote to the operations that can be done on the dev file

static struct file_operations file_ops = {
	.owner = THIS_MODULE,
	// pointing which of our functions should be called when dev file is interacted with
	.open = user_opened_the_file,
    .release = user_closed_the_file,
	.read = user_read_the_file,
	.write = user_wrote_the_file
	
};



// Interrupt handler
static irq_handler_t piirq_irq_handler(unsigned int irq, void *dev_id, struct pt_regs *regs){
    /* Toogle LED */
   gpio_set_value(OffLed, State);
   State = !State;
   gpio_set_value(GreenLed, State);
   gpio_set_value(YellowLed, State);
   gpio_set_value(RedLed, State);
   
   printk(KERN_INFO "piirq: Offled state is : [%d] ", gpio_get_value(OffLed));
   printk(KERN_INFO "piirq: button state is : [%d] ", gpio_get_value(Button));

   Counter++;
   return (irq_handler_t) IRQ_HANDLED;
}
//Function used to reduce the lines of code when initialising multiple GPIO pins
void init_single_gpio(unsigned int pin, char * string, int start_value)
{
	gpio_request(pin,string);
	gpio_direction_output(pin,start_value);
	gpio_export(pin, false);
}
//Function used to reduce the lines of code when releasing multiple GPIO pins
void close_single_gpio(unsigned int pin)
{
   gpio_set_value(pin, 0);
   gpio_unexport(pin);
   gpio_free(pin);
}

int __init piirq_init(void){
	int result = 0;
    pr_info("%s\n", __func__);
    /* https://www.kernel.org/doc/Documentation/pinctrl.txt */
	printk("piirq: IRQ Test");
    printk(KERN_INFO "piirq: Initializing driver\n");

    if (!gpio_is_valid(OffLed) || !gpio_is_valid(GreenLed) || !gpio_is_valid(YellowLed) || !gpio_is_valid(RedLed)){
    	printk(KERN_INFO "piirq: invalid GPIO\n");
    return -ENODEV;
   }

	/* Make it appear in /sys/class/gpio/gpio16 for echo 0 > value */
    	init_single_gpio(OffLed,"OffLed",1);
	init_single_gpio(GreenLed,"GreenLed",0);
	init_single_gpio(YellowLed,"YellowLed",0);
	init_single_gpio(RedLed,"RedLed",0);
	//As the button also includes debounce instruction, it was left separately
	gpio_request(Button, "Button");
	gpio_direction_input(Button);
	gpio_set_debounce(Button, 800); 
	gpio_export(Button, false);


    	Irqnum = gpio_to_irq(Button);
    	printk(KERN_INFO "piirq: The button is mapped to IRQ: %d\n", Irqnum);

 	 result = request_irq(Irqnum,
		  (irq_handler_t) piirq_irq_handler, /* pointer to the IRQ handler method */
		  IRQF_TRIGGER_RISING,
		  "piirq_handler",    /* See this string from user console to identify: cat /proc/interrupts */
		  NULL);

	// Get the device number assigned and create the dev file for interacting with the userspace 
	alloc_chrdev_region(&device_number, 0, 1, DRIVER_NAME); //todo add error checking 
	printk("hopefully device was created with the numbers");

	//Initialise device file 
	cdev_init(&device_itself,&file_ops); //todo add error checking

	// Register the device file
	cdev_add(&device_itself,device_number,1); //todo add error checking

	//Create the device class
	device_class = class_create(THIS_MODULE,DRIVER_CLASS); // todo add error checking

	//Create the device file itself
	device_create(device_class,NULL,device_number, NULL, DRIVER_NAME); //todo add error checking

	
	

    printk("piirq loaded\n");
    return 0;
}
void __exit piirq_exit(void){
   
	close_single_gpio(OffLed);
	close_single_gpio(RedLed);
	close_single_gpio(YellowLed);
	close_single_gpio(GreenLed);
	free_irq(Irqnum, NULL);
 	close_single_gpio(Button);  	

	// Close up everything related to the dev file
	cdev_del(&device_itself);
	device_destroy(device_class, device_number);
	class_destroy(device_class);
	unregister_chrdev(device_number, DRIVER_NAME);


	printk("piirq unloaded\n");
}
module_init(piirq_init);
module_exit(piirq_exit);
MODULE_LICENSE("GPL");
MODULE_AUTHOR("Hubert Januszewski CMP408");
MODULE_DESCRIPTION("Module for CPU utilisation display using LEDs and hybrid cloud control");
MODULE_VERSION("0.1");
